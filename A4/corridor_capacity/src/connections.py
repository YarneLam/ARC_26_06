"""Infer which spaces meet a doorway on the selected corridor segment."""

from dataclasses import dataclass
import math

import ifcopenshell.geom
from ifcopenshell.util.element import get_container, get_parent
from ifcopenshell.util.shape import get_vertices
from shapely.geometry import LineString, MultiPoint, Point
from shapely.ops import nearest_points

from .occupancy import is_reference_area
from .width import floor_geometry


PROBE_OFFSETS_M = (0.05, 0.12, 0.22, 0.35)
FLOOR_TOLERANCE_M = 0.25


@dataclass(frozen=True)
class Doorway:
    x: float
    y: float
    z: float
    normal_x: float
    normal_y: float
    half_depth: float
    source: str

    def probe(self, side, offset):
        distance = side * (self.half_depth + offset)
        return Point(self.x + distance * self.normal_x, self.y + distance * self.normal_y)


def containing_storey(space):
    parent = get_parent(space)
    while parent is not None and not parent.is_a("IfcBuildingStorey"):
        parent = get_parent(parent)
    return parent


def doorway_from_shape(settings, element, source):
    shape = ifcopenshell.geom.create_shape(settings, element)
    vertices = get_vertices(shape.geometry)
    if len(vertices) == 0:
        raise ValueError("Doorway has no vertices.")
    rectangle = MultiPoint(vertices[:, :2]).minimum_rotated_rectangle
    if rectangle.geom_type != "Polygon":
        raise ValueError("Doorway has no horizontal outline.")

    corners = list(rectangle.exterior.coords)
    edges = list(zip(corners, corners[1:]))
    first, last = max(edges, key=lambda edge: math.dist(*edge))
    width = math.dist(first, last)
    depth = min(math.dist(*edge) for edge in edges)
    if depth >= 0.6 * width:
        raise ValueError("Doorway geometry does not identify a clear side-to-side direction.")

    center = rectangle.centroid
    return Doorway(
        center.x, center.y, float(vertices[:, 2].min()),
        (first[1] - last[1]) / width, (last[0] - first[0]) / width,
        depth / 2, source,
    )


def doorway_geometry(settings, door):
    fills = door.FillsVoids
    if len(fills) == 1:
        try:
            return doorway_from_shape(settings, fills[0].RelatingOpeningElement, "opening_geometry")
        except (RuntimeError, ValueError):
            pass
    return doorway_from_shape(settings, door, "door_geometry")


def room_on_side(doorway, side, footprints):
    for offset in PROBE_OFFSETS_M:
        point = doorway.probe(side, offset)
        matches = sorted(
            guid for guid, (polygon, elevation) in footprints.items()
            if abs(doorway.z - elevation) <= FLOOR_TOLERANCE_M and polygon.covers(point)
        )
        if matches:
            return matches, point
    return [], None


def connects_to_segment(point, footprint, route, station):
    center = route.interpolate(station)
    return point.equals(center) or footprint.covers(LineString([point, center]))


def corridor_connections(model, corridor, geometry, start, end):
    storey = containing_storey(corridor)
    if storey is None:
        raise ValueError("The selected corridor needs an IfcBuildingStorey in its spatial hierarchy.")

    spaces = {
        space.GlobalId: space for space in model.by_type("IfcSpace")
        if containing_storey(space) == storey and not is_reference_area(space)
    }
    corridor_guid = corridor.GlobalId
    footprints = {corridor_guid: geometry}
    missing_footprints = []
    for guid, space in spaces.items():
        if guid == corridor_guid:
            continue
        try:
            footprints[guid] = floor_geometry(space)
        except (RuntimeError, ValueError):
            missing_footprints.append(guid)

    route = LineString([start, end])
    footprint, elevation = geometry
    route_footprint = footprint.buffer(0.000001)
    direction = ((end[0] - start[0]) / route.length, (end[1] - start[1]) / route.length)
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    linked_doors = []
    unlocated = []

    for door in model.by_type("IfcDoor"):
        if get_container(door, ifc_class="IfcBuildingStorey") != storey:
            continue
        try:
            doorway = doorway_geometry(settings, door)
        except (RuntimeError, ValueError):
            unlocated.append(door.GlobalId)
            continue
        station = (doorway.x - start[0]) * direction[0] + (doorway.y - start[1]) * direction[1]
        if not 0 <= station <= route.length or abs(doorway.z - elevation) > FLOOR_TOLERANCE_M:
            continue

        sides = [room_on_side(doorway, side, footprints) for side in (-1, 1)]
        corridor_points = [point for matches, point in sides if corridor_guid in matches]
        if not corridor_points:
            center = Point(doorway.x, doorway.y)
            if center.distance(footprint) > doorway.half_depth + PROBE_OFFSETS_M[-1]:
                continue
            corridor_points = [nearest_points(route_footprint, center)[0]]
        if not any(connects_to_segment(point, route_footprint, route, station) for point in corridor_points):
            continue

        first, second = (matches for matches, _ in sides)
        pair = first + second
        valid_pair = len(first) == len(second) == 1 and first != second and corridor_guid in pair
        linked_doors.append({
            "door_guid": door.GlobalId,
            "geometry_source": doorway.source,
            "center_xy_m": [round(doorway.x, 4), round(doorway.y, 4)],
            "station_m": round(station, 4),
            "candidate_space_guids_by_side": [first, second],
            "adjacent_space_guid": next((guid for guid in pair if guid != corridor_guid), None) if valid_pair else None,
            "status": "inferred" if valid_pair else "needs_review",
        })

    return storey, spaces, {
        "door_links": sorted(linked_doors, key=lambda door: (door["station_m"], door["door_guid"])),
        "unlocated_storey_door_guids": sorted(unlocated),
        "spaces_without_usable_footprint": sorted(missing_footprints),
        "probe_offsets_beyond_doorway_m": list(PROBE_OFFSETS_M),
        "floor_tolerance_m": FLOOR_TOLERANCE_M,
    }
