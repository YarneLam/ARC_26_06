"""Run corridor and occupancy screening across every modeled IFC storey."""

from collections import Counter, defaultdict
import re

from ifcopenshell.util.element import get_container
from shapely.errors import GEOSException

from settings import (
    BR18_ROOM_USE, DOCUMENTED_ROOM_LOADS, EXTRA_CORRIDOR_GUIDS, VERIFIED_CORRIDOR_ROOM_GUIDS,
)

from .connections import containing_storey, explicit_door_spaces, space_footprints, storey_door_links
from .main import capacity_screening, room_loads, space_label
from .occupancy import is_reference_area, load_reference
from .width import corridor_width_measurement


CORRIDOR_WORDS = re.compile(
    r"(?<!\w)(?:corridors?|hallways?|korridor(?:er)?|gang|gangareal|fordelingsgang|flugtvejsgang)(?!\w)",
    re.IGNORECASE,
)
CIRCULATION_LABELS = {"circulation", "circulation area", "circulation space"}


def is_corridor(space):
    return any(
        CORRIDOR_WORDS.search(label or "") or " ".join((label or "").split()).casefold() in CIRCULATION_LABELS
        for label in (space.LongName, space.Name, space.ObjectType)
    )


def storey_name(storey):
    return storey.Name or storey.LongName or "Unnamed storey"


def width_for_corridor(geometry):
    if geometry is None:
        return {"minimum_m": None, "issue": "Missing usable corridor floor footprint"}
    try:
        width = corridor_width_measurement(geometry[0])
    except GEOSException:
        return {"minimum_m": None, "issue": "Could not section the corridor floor footprint"}
    if width["minimum_m"] is None:
        width["issue"] = "No supported opposing-edge cross-section"
    elif width["measured_components"] < width["components"]:
        width["issue"] = "One or more disconnected footprint components could not be measured"
    return width


def corridor_result(model, corridor, storey, spaces, all_corridors, geometry, links, reference,
                    route_rooms, room_uses, documented_loads):
    inferred = {link["adjacent_space_guid"] for link in links if link["adjacent_space_guid"]}
    inferred -= all_corridors
    assignment = route_rooms.get(corridor.GlobalId)
    assigned = inferred if assignment is None else set(assignment)
    if assigned - spaces.keys() or assigned.intersection(all_corridors):
        raise ValueError(f"Route rooms for {space_label(corridor)} must be non-corridor spaces on its storey.")

    width = width_for_corridor(geometry)
    rooms = room_loads(model, spaces, assigned, reference["occupancy_densities"], room_uses, documented_loads)
    capacity = capacity_screening(width["minimum_m"], rooms, assignment is not None and "issue" not in width, reference)
    return {
        "corridor_guid": corridor.GlobalId,
        "corridor": space_label(corridor),
        "space_number": corridor.Name,
        "storey_guid": storey.GlobalId,
        "storey": storey_name(storey),
        "room_assignment": "verified_room_list" if assignment is not None else "inferred_direct_rooms",
        "width": width,
        "capacity": capacity,
        "door_links": sorted(links, key=lambda link: link["door_guid"]),
        "rooms": rooms,
    }


def analyse(model, *, extra_corridor_guids=None, route_rooms=None, room_uses=None, documented_loads=None):
    """Return corridor results, room evidence, and model coverage by storey."""
    extra_corridor_guids = set(EXTRA_CORRIDOR_GUIDS if extra_corridor_guids is None else extra_corridor_guids)
    route_rooms = VERIFIED_CORRIDOR_ROOM_GUIDS if route_rooms is None else route_rooms
    room_uses = BR18_ROOM_USE if room_uses is None else room_uses
    documented_loads = DOCUMENTED_ROOM_LOADS if documented_loads is None else documented_loads
    reference = load_reference()
    if set(room_uses.values()) - reference["occupancy_densities"].keys():
        raise ValueError("BR18_ROOM_USE must use a category in br18_reference.json.")

    spaces = {space.GlobalId: space for space in model.by_type("IfcSpace") if not is_reference_area(space)}
    all_corridors = {
        guid for guid, space in spaces.items() if guid in extra_corridor_guids or is_corridor(space)
    }
    if extra_corridor_guids - spaces.keys() or route_rooms.keys() - all_corridors:
        raise ValueError("A configured corridor GUID does not match an eligible space in this IFC.")

    by_storey = defaultdict(dict)
    space_storeys = {}
    for guid, space in spaces.items():
        storey = containing_storey(space)
        by_storey[storey][guid] = space
        space_storeys[guid] = storey

    explicit_links = explicit_door_spaces(model)
    doors_by_storey = defaultdict(list)
    for door in model.by_type("IfcDoor"):
        storey = get_container(door, ifc_class="IfcBuildingStorey")
        if storey is None:
            related_storeys = {space_storeys.get(guid) for guid in explicit_links.get(door.GlobalId, ())}
            if len(related_storeys) == 1:
                storey = next(iter(related_storeys))
        doors_by_storey[storey].append(door)

    storeys = []
    corridors = []
    for storey in sorted(model.by_type("IfcBuildingStorey"), key=lambda level: (level.Elevation or 0, storey_name(level))):
        floor_spaces = by_storey[storey]
        floor_corridors = all_corridors.intersection(floor_spaces)
        doors = doors_by_storey[storey]
        footprints, missing, unlocated = {}, [], []
        floor_results = []
        if floor_corridors:
            footprints, missing = space_footprints(floor_spaces)
            links, unlocated = storey_door_links(doors, floor_spaces, footprints, floor_corridors, explicit_links)
            for guid in sorted(floor_corridors, key=lambda item: (space_label(floor_spaces[item]), item)):
                floor_results.append(corridor_result(
                    model, floor_spaces[guid], storey, floor_spaces, all_corridors, footprints.get(guid), links[guid],
                    reference, route_rooms, room_uses, documented_loads,
                ))
        corridors.extend(floor_results)
        measured = sum(row["width"]["minimum_m"] is not None for row in floor_results)
        coverage = "No corridor space identified"
        if floor_corridors:
            partial_width = any("issue" in row["width"] for row in floor_results)
            coverage = "Width coverage incomplete" if partial_width else "Corridors screened"
        storeys.append({
            "storey_guid": storey.GlobalId,
            "storey": storey_name(storey),
            "space_count": len(floor_spaces),
            "door_count": len(doors),
            "corridors_found": len(floor_corridors),
            "corridors_with_width": measured,
            "coverage_status": coverage,
            "spaces_without_usable_footprint": missing,
            "unlocated_door_guids": unlocated,
        })

    counts = Counter(room["room_guid"] for corridor in corridors for room in corridor["rooms"])
    for corridor in corridors:
        for room in corridor["rooms"]:
            room["appears_in_multiple_corridors"] = counts[room["room_guid"]] > 1

    header = model.header.file_name
    return {
        "scope": "whole_ifc",
        "model": {"ifc_header_name": header.name, "ifc_export_timestamp": header.time_stamp, "schema": model.schema_identifier},
        "storeys": storeys,
        "corridors": corridors,
        "corridors_without_storey_guids": sorted(all_corridors.intersection(by_storey[None])),
        "doors_without_storey_guids": sorted(door.GlobalId for door in doors_by_storey[None]),
        "references": {
            "common_access_width": {**reference["common_access_width"], "minimum_m": float(reference["common_access_width"]["minimum_m"])},
            "assembly_route_width": {**reference["assembly_route_width"], "metres_per_person": float(reference["assembly_route_width"]["metres_per_person"])},
            "occupancy": reference["occupancy_source"],
        },
        "limitations": [
            "Corridor coverage relies on modeled, identifiable IfcSpace records with storey membership.",
            "Automatic width screens facing edges in the floor footprint. Verify reported bottlenecks, branches and clear widths on the plan.",
            "The default load is from directly connected rooms. Verify upstream flows, alternative exits and cross-storey assignments separately.",
            "A room can serve multiple corridors. Avoid adding per-corridor occupant totals.",
            "The Annex 4 width rate is a screening scenario. Confirm its applicability for each route.",
        ],
    }
