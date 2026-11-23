"""Measure modeled floor-space widths for corridors and selected route segments."""

import math

import ifcopenshell.geom
from ifcopenshell.util.shape import get_faces, get_vertices
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


SAMPLE_SPACING_M = 0.10
MIN_OPPOSING_SPAN_M = 0.25
EDGE_TOLERANCE_M = 0.000001


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


def boundary_edges(polygon):
    edges = []
    polygon = orient(polygon, sign=1)
    for ring in (polygon.exterior, *polygon.interiors):
        for start, end in zip(ring.coords, ring.coords[1:]):
            length = math.dist(start, end)
            if length >= MIN_OPPOSING_SPAN_M:
                direction = ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
                edges.append((start, end, direction, length))
    return edges


def opposing_sections(polygon):
    """Sample cross-sections between facing edges with a shared longitudinal span."""
    polygon = polygon.simplify(0.00001, preserve_topology=True)
    inside = polygon.buffer(EDGE_TOLERANCE_M)
    edges = boundary_edges(polygon)
    for start, _, tangent, length in edges:
        tx, ty = tangent
        nx, ny = -ty, tx
        for other_start, other_end, other_tangent, _ in edges:
            if tx * other_tangent[0] + ty * other_tangent[1] > -0.94:
                continue
            projections = [(x - start[0]) * tx + (y - start[1]) * ty for x, y in (other_start, other_end)]
            begin = max(0., min(projections))
            end = min(length, max(projections))
            span = end - begin
            if span < MIN_OPPOSING_SPAN_M:
                continue

            samples = math.ceil(span / SAMPLE_SPACING_M)
            for index in range(samples):
                station = begin + span * (index + 0.5) / samples
                fraction = (station - projections[0]) / (projections[1] - projections[0])
                first = (start[0] + tx * station, start[1] + ty * station)
                second = tuple(a + fraction * (b - a) for a, b in zip(other_start, other_end))
                width = (second[0] - first[0]) * nx + (second[1] - first[1]) * ny
                if width <= EDGE_TOLERANCE_M:
                    continue
                mid = Point((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
                section = LineString([first, second])
                if polygon.contains(mid) and inside.covers(section):
                    yield width, section, span


def corridor_width_measurement(footprint):
    """Screen each footprint component and report the narrowest sampled cross-section."""
    components = [footprint] if footprint.geom_type == "Polygon" else list(footprint.geoms)
    picked = None
    measurements = 0
    measured_components = 0
    for polygon in components:
        component_count = 0
        for candidate in opposing_sections(polygon):
            component_count += 1
            if picked is None or (round(candidate[0], 6), -candidate[2]) < (round(picked[0], 6), -picked[2]):
                picked = candidate
        if component_count:
            measured_components += 1
            measurements += component_count

    result = {
        "method": "opposing_footprint_edges",
        "minimum_m": None,
        "components": len(components),
        "measured_components": measured_components,
        "cross_sections_sampled": measurements,
        "max_sample_spacing_m": SAMPLE_SPACING_M,
        "minimum_opposing_span_m": MIN_OPPOSING_SPAN_M,
    }
    if picked is not None:
        width, section, span = picked
        result.update(
            minimum_m=round(width, 6),
            cross_section_xy_m=[list(section.coords[0]), list(section.coords[-1])],
            opposing_span_m=round(span, 6),
        )
    return result


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
