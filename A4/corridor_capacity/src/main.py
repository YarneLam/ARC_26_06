"""Run the A4 corridor-capacity workflow and return JSON-compatible evidence."""

from settings import (
    BR18_ROOM_USE, CORRIDOR_LABEL, DOCUMENTED_ROOM_LOADS, ROUTE_AXIS_M, VERIFIED_ROUTE_ROOM_GUIDS,
)

from .connections import corridor_connections
from .occupancy import NON_ROOM_LOAD, estimate_occupancy, load_reference
from .width import floor_geometry, width_measurement


def space_label(space):
    return " ".join((space.LongName or space.Name or "Unnamed space").split())


def selected_corridor(model, selector):
    matches = [
        space for space in model.by_type("IfcSpace")
        if space.GlobalId == selector or space_label(space).casefold() == selector.casefold()
    ]
    if len(matches) != 1:
        raise ValueError("Set CORRIDOR_LABEL in settings.py to a unique IfcSpace name or GUID.")
    return matches[0]


def documented_occupancy(entry):
    people = entry.get("people")
    source = entry.get("source")
    if type(people) is not int or people < 0 or not isinstance(source, str) or not source.strip():
        raise ValueError("A documented room load must have nonnegative integer people and a source.")
    return {"status": "Documented design load", "people_min": people, "people_max": people, "source": source}


def room_loads(model, spaces, room_guids, densities, room_uses, documented_loads):
    rooms = []
    for guid in sorted(room_guids):
        space = spaces[guid]
        if guid in documented_loads:
            estimate = documented_occupancy(documented_loads[guid])
        else:
            estimate = estimate_occupancy(model, space, densities, room_uses.get(guid))
        rooms.append({"room_guid": guid, "room": space_label(space), **estimate})
    return sorted(rooms, key=lambda room: (room["room"], room["room_guid"]))


def capacity_screening(width, rooms, assignment_verified, references):
    known = [room for room in rooms if "people_max" in room]
    unresolved = [room["room_guid"] for room in rooms if "people_max" not in room and room["status"] != NON_ROOM_LOAD]
    access_width = float(references["common_access_width"]["minimum_m"])
    annex_rate = float(references["assembly_route_width"]["metres_per_person"])
    known_range = [sum(room[key] for room in known) for key in ("people_min", "people_max")]
    required = [round(max(access_width, people * annex_rate), 6) for people in known_range]
    known_comparison = None
    if known and width is not None:
        known_comparison = "at_or_above_reference" if width >= required[1] else "below_upper_reference"

    return {
        "status": "screening_complete" if width is not None and assignment_verified and known and not unresolved else "review_required",
        "known_room_load_people": known_range if known else None,
        "rooms_missing_occupancy_guids": unresolved,
        "required_width_for_known_load_m": required if known else None,
        "known_load_width_comparison": known_comparison,
        "common_access_width_reference_m": access_width,
        "common_access_width_comparison": (
            None if width is None else "at_or_above_reference" if width >= access_width else "below_reference"
        ),
        "annex_4_scenario_metres_per_person": annex_rate,
    }


def analyse(
    model, *, corridor_selector=CORRIDOR_LABEL, route_axis=ROUTE_AXIS_M,
    verified_route_rooms=VERIFIED_ROUTE_ROOM_GUIDS, room_uses=None, documented_loads=None,
):
    """Analyze a straight corridor segment and its configured or inferred room load."""
    room_uses = BR18_ROOM_USE if room_uses is None else room_uses
    documented_loads = DOCUMENTED_ROOM_LOADS if documented_loads is None else documented_loads
    reference = load_reference()
    densities = reference["occupancy_densities"]
    if set(room_uses.values()) - densities.keys():
        raise ValueError("BR18_ROOM_USE must use a category in br18_reference.json.")

    corridor = selected_corridor(model, corridor_selector)
    start, end = route_axis
    geometry = floor_geometry(corridor)
    width = width_measurement(geometry[0], start, end)
    storey, spaces, connections = corridor_connections(model, corridor, geometry, start, end)

    inferred = {door["adjacent_space_guid"] for door in connections["door_links"] if door["status"] == "inferred"}
    assigned = set(verified_route_rooms) if verified_route_rooms else inferred
    if assigned - spaces.keys() or corridor.GlobalId in assigned:
        raise ValueError("Verified route room GUIDs must identify other spaces on the selected storey.")

    rooms = room_loads(model, spaces, assigned, densities, room_uses, documented_loads)
    capacity = capacity_screening(width["minimum_m"], rooms, bool(verified_route_rooms), reference)
    header = model.header.file_name
    return {
        "model": {"ifc_header_name": header.name, "ifc_export_timestamp": header.time_stamp, "schema": model.schema_identifier},
        "scenario": {
            "corridor_guid": corridor.GlobalId,
            "corridor": space_label(corridor),
            "storey": storey.Name,
            "axis_xy_m": [list(start), list(end)],
            "room_assignment": "verified_room_list" if verified_route_rooms else "inferred_direct_rooms",
            "verified_route_room_guids": sorted(verified_route_rooms),
        },
        "width": width,
        "connections": connections,
        "rooms": rooms,
        "capacity": capacity,
        "references": {
            "occupancy": reference["occupancy_source"],
            "common_access_width": {**reference["common_access_width"], "minimum_m": capacity["common_access_width_reference_m"]},
            "assembly_route_width": {**reference["assembly_route_width"], "metres_per_person": capacity["annex_4_scenario_metres_per_person"]},
        },
        "limitations": [
            "An inferred doorway link is a topology candidate. Check unusual doors and open passages against the plan.",
            "The default load counts inferred direct rooms once and assumes their occupants use this segment. Review upstream rooms and exits on the egress plan.",
            "The sampled floor-space width excludes checks for door clear opening, obstructions, and the rest of the escape route.",
            "The Annex 4 rate is used as a screening scenario. Its applicability depends on the fire strategy and actual use.",
        ],
    }
