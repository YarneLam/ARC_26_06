"""Measure the modeled floor-space width along a straight route segment."""

import math

import ifcopenshell.geom
from ifcopenshell.util.shape import get_faces, get_vertices
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union


SAMPLE_SPACING_M = 0.10


def floor_geometry(space):
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    shape = ifcopenshell.geom.create_shape(settings, space)
    vertices = get_vertices(shape.geometry)
    if len(vertices) == 0:
        raise ValueError("The space has no tessellated geometry.")

    base_z = vertices[:, 2].min()
    floor_faces = []
    for face in get_faces(shape.geometry):
        triangle = vertices[face]
        if max(abs(z - base_z) for z in triangle[:, 2]) <= 0.00001:
            polygon = Polygon(triangle[:, :2])
            if polygon.area > 0:
                floor_faces.append(polygon)

    footprint = unary_union(floor_faces)
    if footprint.is_empty or not footprint.is_valid:
        raise ValueError("The space has no usable horizontal floor footprint.")
    return footprint, float(base_z)


def minimum_width(footprint, start, end):
    if not all(math.isfinite(value) for value in (*start, *end)):
        raise ValueError("Route coordinates must be finite.")
    route = LineString([start, end])
    if route.length == 0:
        raise ValueError("Use two distinct points to define a route segment.")
    if not footprint.covers(route):
        raise ValueError("The whole route segment must lie inside the floor footprint.")

    dx = (end[0] - start[0]) / route.length
    dy = (end[1] - start[1]) / route.length
    min_x, min_y, max_x, max_y = footprint.bounds
    reach = math.hypot(max_x - min_x, max_y - min_y)
    steps = math.ceil(route.length / SAMPLE_SPACING_M)
    sections = []
    for step in range(steps + 1):
        station = route.length * step / steps
        center = route.interpolate(station)
        cross_section = LineString([
            (center.x - dy * reach, center.y + dx * reach),
            (center.x + dy * reach, center.y - dx * reach),
        ])
        cut = footprint.intersection(cross_section)
        nearby = [
            part for part in getattr(cut, "geoms", [cut])
            if part.geom_type == "LineString" and part.distance(center) < 0.000001
        ]
        if len(nearby) != 1:
            raise ValueError(f"Could not establish one width at station {station:.2f} m.")
        sections.append((nearby[0].length, station, nearby[0]))

    return min(sections, key=lambda item: item[0])


def width_measurement(footprint, start, end):
    width, station, section = minimum_width(footprint, start, end)
    return {
        "minimum_m": round(width, 6),
        "station_m": round(station, 6),
        "cross_section_xy_m": [list(section.coords[0]), list(section.coords[-1])],
        "max_sample_spacing_m": SAMPLE_SPACING_M,
    }


def report_width(space, start, end, reference):
    footprint, _ = floor_geometry(space)
    width, station, section = minimum_width(footprint, start, end)
    endpoints = " to ".join(f"({x:.3f}, {y:.3f})" for x, y in (section.coords[0], section.coords[-1]))
    target = float(reference["minimum_m"])
    status = "AT OR ABOVE REFERENCE" if width >= target else "BELOW REFERENCE"
    print(f"Minimum sampled floor-space width: {width:.3f} m")
    print(f"Smallest cross-section at route station: {station:.2f} m")
    print(f"Smallest cross-section endpoints (model X/Y in m): {endpoints}")
    print(f"Common access width reference ({reference['locator']}): {target:.2f} m | {status}")
    print("Scope: selected straight segment of the IfcSpace floor footprint.")
