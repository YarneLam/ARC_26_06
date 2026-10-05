"""
IFC CIRCULATION + PEDESTRIAN FLOW ANALYSIS
==========================================

Designed for:
    Blender + Bonsai / BlenderBIM

Can also run standalone with:
    python ifc_circulation_flow.py model.ifc

WHAT IT DOES
------------
1. Finds all IfcSpace objects.
2. Finds all IfcDoor objects.
3. Connects doors to spaces using:
       A. IfcRelSpaceBoundary, when available
       B. wall/opening relationships
       C. geometric door-to-space matching as fallback
4. Builds a circulation graph.
5. Calculates shortest circulation path.
6. Calculates maximum pedestrian flow.
7. Calculates door capacities.
8. Reports bottlenecks.
9. Reports room areas and occupant capacities.
10. Creates an optional topology image.
11. Creates an optional CSV report.
12. Can optionally create 3D flow curves in Blender.

IMPORTANT
---------
The pedestrian flow values are illustrative engineering assumptions.
They are NOT a substitute for the applicable building/fire/accessibility
code or a formal egress calculation.

For your model:
    - IfcSpace objects are expected.
    - IfcRelSpaceBoundary is NOT required.
    - Geometry is used when boundaries are missing.
"""

import sys
import os
import csv
import math

import ifcopenshell
import ifcopenshell.util.element as element
import ifcopenshell.util.unit as unit_util


# ==========================================================================
# NETWORKX
# ==========================================================================

try:
    import networkx as nx
except ImportError:
    raise SystemExit(
        "networkx is required.\n"
        "Install it in Blender's Python environment."
    )


# ==========================================================================
# CONFIGURATION
# ==========================================================================

# Persons / second / metre of clear door width.
# Illustrative value.
FLOW_COEFFICIENT = 1.3

# Used if a space has no usable area.
DEFAULT_ROOM_CAPACITY = 50

# Illustrative occupancy density.
M2_PER_PERSON = 10.0

# Used if door width cannot be found.
DEFAULT_DOOR_WIDTH = 0.9

# Door utilisation above this percentage is reported.
BOTTLENECK_THRESHOLD = 90.0

# Output files.
DEFAULT_MAP_PATH = "circulation_map.png"
DEFAULT_CSV_PATH = "room_areas_and_capacities.csv"

# Exterior node.
OUTSIDE = "OUTSIDE"

# IFC project length-unit -> metres.
UNIT_SCALE = 1.0


# ==========================================================================
# GLOBAL GEOMETRY CACHE
# ==========================================================================

_MESH_CACHE = {}


# ==========================================================================
# MODEL LOADING
# ==========================================================================

def load_model(ifc_path=None):
    """
    Load IFC from disk or from the active Bonsai/BlenderBIM project.
    """

    # --------------------------------------------------------------
    # Explicit IFC path
    # --------------------------------------------------------------

    if ifc_path:

        if not os.path.exists(ifc_path):
            raise FileNotFoundError(
                f"IFC file not found:\n{ifc_path}"
            )

        print(f"[model] Opening IFC: {ifc_path}")

        return ifcopenshell.open(ifc_path)

    # --------------------------------------------------------------
    # Bonsai
    # --------------------------------------------------------------

    try:

        import bonsai.tool as tool

        model = tool.Ifc.get()

        if model is not None:

            print(
                "[model] Using active IFC project "
                "(bonsai.tool)"
            )

            return model

    except Exception as e:

        print(f"[model] Bonsai lookup failed: {e}")

    # --------------------------------------------------------------
    # Older BlenderBIM
    # --------------------------------------------------------------

    try:

        import blenderbim.tool as tool

        model = tool.Ifc.get()

        if model is not None:

            print(
                "[model] Using active IFC project "
                "(blenderbim.tool)"
            )

            return model

    except Exception as e:

        print(f"[model] BlenderBIM lookup failed: {e}")

    raise RuntimeError(
        "\nNo IFC model found.\n\n"
        "Make sure:\n"
        "1. Your IFC model is open in Blender/Bonsai, or\n"
        "2. You provide an IFC path to main()."
    )


# ==========================================================================
# UNITS
# ==========================================================================

def set_unit_scale(model):

    global UNIT_SCALE

    try:

        UNIT_SCALE = float(
            unit_util.calculate_unit_scale(model)
        )

    except Exception as e:

        UNIT_SCALE = 1.0

        print(
            "[units] Could not determine IFC unit scale."
        )

        print(
            f"[units] Error: {e}"
        )

        print(
            "[units] Assuming metres."
        )

    print(
        f"[units] 1 IFC length unit = "
        f"{UNIT_SCALE} metres"
    )


# ==========================================================================
# GENERAL HELPERS
# ==========================================================================

def safe_float(value):

    try:

        value = float(value)

        if value > 0:
            return value

    except Exception:
        pass

    return None


def space_name(space):

    return str(
        getattr(space, "LongName", None)
        or getattr(space, "Name", None)
        or space.GlobalId[:8]
    )


def door_name(door):

    return str(
        getattr(door, "Name", None)
        or door.GlobalId[:8]
    )


# ==========================================================================
# DOOR WIDTH
# ==========================================================================

def get_door_width(door):
    """
    Return door width in metres.

    Tries:
        Qto_DoorBaseQuantities.Width
        custom Width/ClearWidth properties
        IfcDoor OverallWidth
        default width
    """

    try:

        psets = element.get_psets(
            door,
            psets_only=False
        )

    except Exception:

        psets = {}

    width = None

    # --------------------------------------------------------------
    # QTO
    # --------------------------------------------------------------

    qto = psets.get(
        "Qto_DoorBaseQuantities",
        {}
    )

    width = safe_float(
        qto.get("Width")
    )

    # --------------------------------------------------------------
    # Other property sets
    # --------------------------------------------------------------

    if width is None:

        for props in psets.values():

            if not isinstance(props, dict):
                continue

            for key in (
                "ClearWidth",
                "Clear Width",
                "Width",
                "OverallWidth"
            ):

                value = safe_float(
                    props.get(key)
                )

                if value:

                    width = value
                    break

            if width:
                break

    # --------------------------------------------------------------
    # IFC attribute
    # --------------------------------------------------------------

    if width is None:

        width = safe_float(
            getattr(
                door,
                "OverallWidth",
                None
            )
        )

    # --------------------------------------------------------------
    # Result
    # --------------------------------------------------------------

    if width:

        return width * UNIT_SCALE

    return DEFAULT_DOOR_WIDTH


# ==========================================================================
# SPACE AREA
# ==========================================================================

def get_room_area(space):
    """
    Return floor area in m2.

    First attempts IFC quantity/property data.

    If unavailable, falls back to geometric calculation.
    """

    try:

        psets = element.get_psets(
            space,
            psets_only=False
        )

    except Exception:

        psets = {}

    # --------------------------------------------------------------
    # Standard IFC QTO
    # --------------------------------------------------------------

    qto = psets.get(
        "Qto_SpaceBaseQuantities",
        {}
    )

    area = safe_float(
        qto.get("NetFloorArea")
    )

    if area is None:

        area = safe_float(
            qto.get("GrossFloorArea")
        )

    # --------------------------------------------------------------
    # Custom properties
    # --------------------------------------------------------------

    if area is None:

        for props in psets.values():

            if not isinstance(props, dict):
                continue

            for key in (
                "NetFloorArea",
                "GrossFloorArea",
                "FloorArea",
                "Area"
            ):

                value = safe_float(
                    props.get(key)
                )

                if value:

                    area = value
                    break

            if area:
                break

    # --------------------------------------------------------------
    # IFC area quantities are normally already m2.
    # Do NOT apply length UNIT_SCALE here.
    # --------------------------------------------------------------

    if area:

        return area

    # --------------------------------------------------------------
    # Geometry fallback
    # --------------------------------------------------------------

    return geometric_floor_area(space)


def room_capacity(area):

    if area > 0:

        return int(
            area / M2_PER_PERSON
        )

    return DEFAULT_ROOM_CAPACITY


# ==========================================================================
# IFC GEOMETRY
# ==========================================================================

def _shape_mesh(entity):

    """
    Create an IfcOpenShell geometry mesh.

    Returns:
        vertices
        faces

    Coordinates are converted to metres.
    """

    try:

        import numpy as np
        import ifcopenshell.geom as geom

    except ImportError:

        print(
            "[geometry] NumPy / IfcOpenShell geometry unavailable."
        )

        return None

    try:

        settings = geom.settings()

        # Different IfcOpenShell versions use different syntax.
        try:

            settings.set(
                "use-world-coords",
                True
            )

        except Exception:

            settings.set(
                settings.USE_WORLD_COORDS,
                True
            )

        shape = geom.create_shape(
            settings,
            entity
        )

        verts = np.array(
            shape.geometry.verts,
            dtype=float
        ).reshape(-1, 3)

        faces = np.array(
            shape.geometry.faces,
            dtype=int
        ).reshape(-1, 3)

        if len(verts) == 0:
            return None

        if len(faces) == 0:
            return None

        # IfcOpenShell geometry uses IFC model units.
        # Convert coordinates to metres.
        verts *= UNIT_SCALE

        return verts, faces

    except Exception as e:

        print(
            f"[geometry] Could not create geometry for "
            f"{entity.is_a()} "
            f"{getattr(entity, 'GlobalId', '')}: {e}"
        )

        return None


# ==========================================================================
# SPACE GEOMETRY
# ==========================================================================

def _space_geo(space):

    """
    Cached geometric information for an IfcSpace.
    """

    import numpy as np

    gid = space.GlobalId

    if gid in _MESH_CACHE:

        return _MESH_CACHE[gid]

    mesh = _shape_mesh(space)

    if mesh is None:

        _MESH_CACHE[gid] = None

        return None

    vertices, faces = mesh

    try:

        triangles = vertices[faces]

        # Bounding box.
        lo = vertices.min(
            axis=0
        )

        hi = vertices.max(
            axis=0
        )

        volume = float(
            np.prod(
                np.maximum(
                    hi - lo,
                    0
                )
            )
        )

        # ----------------------------------------------------------
        # Estimate floor area from downward-facing triangles.
        # ----------------------------------------------------------

        edge1 = (
            triangles[:, 1]
            - triangles[:, 0]
        )

        edge2 = (
            triangles[:, 2]
            - triangles[:, 0]
        )

        cross = np.cross(
            edge1,
            edge2
        )

        magnitude = np.linalg.norm(
            cross,
            axis=1
        )

        valid = magnitude > 1e-12

        normals_z = np.zeros_like(
            magnitude
        )

        normals_z[valid] = (
            cross[valid, 2]
            /
            magnitude[valid]
        )

        downward = normals_z < -0.9

        floor_area = float(
            np.sum(
                0.5
                * magnitude[downward]
            )
        )

        geo = {
            "v": vertices,
            "f": faces,
            "lo": lo,
            "hi": hi,
            "vol": volume,
            "floor_area": floor_area
        }

        _MESH_CACHE[gid] = geo

        return geo

    except Exception as e:

        print(
            f"[geometry] Space geometry calculation failed "
            f"for {space_name(space)}: {e}"
        )

        _MESH_CACHE[gid] = None

        return None


def geometric_floor_area(space):

    geo = _space_geo(space)

    if geo:

        return geo["floor_area"]

    return 0.0


# ==========================================================================
# POINT IN SPACE
# ==========================================================================

def _point_in_mesh(point, vertices, faces):

    """
    Determine whether a point lies inside an IFC space.

    Uses a vertical ray intersection test.
    """

    import numpy as np

    triangles = vertices[faces]

    x = point[0]
    y = point[1]
    z = point[2]

    a = triangles[:, 0, :2]
    b = triangles[:, 1, :2]
    c = triangles[:, 2, :2]

    denominator = (
        (b[:, 1] - c[:, 1])
        *
        (a[:, 0] - c[:, 0])
        +
        (c[:, 0] - b[:, 0])
        *
        (a[:, 1] - c[:, 1])
    )

    valid = (
        np.abs(
            denominator
        )
        > 1e-12
    )

    denominator_safe = np.where(
        valid,
        denominator,
        1.0
    )

    l1 = (
        (b[:, 1] - c[:, 1])
        *
        (x - c[:, 0])
        +
        (c[:, 0] - b[:, 0])
        *
        (y - c[:, 1])
    ) / denominator_safe

    l2 = (
        (c[:, 1] - a[:, 1])
        *
        (x - c[:, 0])
        +
        (a[:, 0] - c[:, 0])
        *
        (y - c[:, 1])
    ) / denominator_safe

    l3 = (
        1.0
        - l1
        - l2
    )

    inside_xy = (
        valid
        &
        (l1 >= 0)
        &
        (l2 >= 0)
        &
        (l3 >= 0)
    )

    intersection_z = (
        l1 * triangles[:, 0, 2]
        +
        l2 * triangles[:, 1, 2]
        +
        l3 * triangles[:, 2, 2]
    )

    intersections_above = (
        inside_xy
        &
        (
            intersection_z
            > z
        )
    )

    return (
        int(
            np.count_nonzero(
                intersections_above
            )
        )
        % 2
        == 1
    )


# ==========================================================================
# FIND SPACE AT POINT
# ==========================================================================

def _space_at(point, space_geometries):

    """
    Return the smallest space containing a point.
    """

    candidates = []

    for space, geo in space_geometries:

        if geo is None:
            continue

        # Bounding box test.
        if (
            point[0]
            < geo["lo"][0]
            or
            point[0]
            >
            geo["hi"][0]
        ):
            continue

        if (
            point[1]
            < geo["lo"][1]
            or
            point[1]
            >
            geo["hi"][1]
        ):
            continue

        if (
            point[2]
            < geo["lo"][2]
            or
            point[2]
            >
            geo["hi"][2]
        ):
            continue

        try:

            inside = _point_in_mesh(
                point,
                geo["v"],
                geo["f"]
            )

        except Exception:

            inside = False

        if inside:

            candidates.append(
                (
                    space,
                    geo
                )
            )

    if not candidates:

        return None

    # If nested spaces exist, choose the smallest.
    candidates.sort(
        key=lambda item:
        item[1]["vol"]
    )

    return candidates[0][0]


# ==========================================================================
# DOOR GEOMETRIC MATCHING
# ==========================================================================

def geometric_door_spaces(
    door,
    space_geometries
):

    """
    Match a door to spaces geometrically.

    The door centre is calculated.

    The door's smallest plan-direction variance is treated as
    the normal direction.

    Points are sampled on both sides of the door.
    """

    import numpy as np

    mesh = _shape_mesh(door)

    if mesh is None:

        return None, None

    vertices, faces = mesh

    if len(vertices) == 0:

        return None, None

    xy = vertices[:, :2]

    # --------------------------------------------------------------
    # Door centre
    # --------------------------------------------------------------

    centre = (
        xy.min(axis=0)
        +
        xy.max(axis=0)
    ) / 2.0

    # --------------------------------------------------------------
    # PCA in plan
    # --------------------------------------------------------------

    try:

        centred = (
            xy
            -
            xy.mean(axis=0)
        )

        covariance = np.cov(
            centred.T
        )

        eigenvalues, eigenvectors = np.linalg.eigh(
            covariance
        )

        # Smallest variance = thickness direction.
        normal = eigenvectors[:, 0]

    except Exception:

        return None, None

    # --------------------------------------------------------------
    # Door Z sampling
    # --------------------------------------------------------------

    min_z = vertices[:, 2].min()
    max_z = vertices[:, 2].max()

    # Use middle of door rather than a hard-coded 1m.
    sample_z = (
        min_z
        +
        0.5
        *
        (
            max_z
            -
            min_z
        )
    )

    # --------------------------------------------------------------
    # Test progressively further from the door.
    # --------------------------------------------------------------

    distances = (
        0.15,
        0.30,
        0.50,
        0.75,
        1.00,
        1.50
    )

    candidate_external = None

    for distance in distances:

        pa_xy = (
            centre
            +
            normal
            * distance
        )

        pb_xy = (
            centre
            -
            normal
            * distance
        )

        pa = np.array(
            [
                pa_xy[0],
                pa_xy[1],
                sample_z
            ]
        )

        pb = np.array(
            [
                pb_xy[0],
                pb_xy[1],
                sample_z
            ]
        )

        space_a = _space_at(
            pa,
            space_geometries
        )

        space_b = _space_at(
            pb,
            space_geometries
        )

        # ----------------------------------------------------------
        # Two different spaces = valid internal connection.
        # ----------------------------------------------------------

        if (
            space_a is not None
            and
            space_b is not None
            and
            space_a.GlobalId
            !=
            space_b.GlobalId
        ):

            return space_a, space_b

        # ----------------------------------------------------------
        # One space + outside = possible external door.
        # ----------------------------------------------------------

        if (
            space_a is not None
            and
            space_b is None
        ):

            candidate_external = (
                space_a,
                None
            )

        elif (
            space_b is not None
            and
            space_a is None
        ):

            candidate_external = (
                None,
                space_b
            )

    if candidate_external:

        return candidate_external

    return None, None


# ==========================================================================
# IFC DOOR/SPACE RELATIONSHIPS
# ==========================================================================

def _unique_spaces(spaces):

    result = {}

    for space in spaces:

        if space is None:
            continue

        try:

            result[
                space.GlobalId
            ] = space

        except Exception:
            pass

    return list(
        result.values()
    )


def _spaces_from_boundaries(door):

    spaces = []

    for boundary in (
        getattr(
            door,
            "ProvidesBoundaries",
            None
        )
        or []
    ):

        space = getattr(
            boundary,
            "RelatingSpace",
            None
        )

        if (
            space is not None
            and
            space.is_a("IfcSpace")
        ):

            spaces.append(
                space
            )

    return _unique_spaces(
        spaces
    )


def _spaces_from_wall(door):

    """
    Door -> opening -> wall -> space boundaries.

    Only accepted when exactly two spaces are found.
    """

    spaces = []

    for fill in (
        getattr(
            door,
            "FillsVoids",
            None
        )
        or []
    ):

        opening = getattr(
            fill,
            "RelatingOpeningElement",
            None
        )

        if opening is None:
            continue

        for void in (
            getattr(
                opening,
                "VoidsElements",
                None
            )
            or []
        ):

            wall = getattr(
                void,
                "RelatingBuildingElement",
                None
            )

            if wall is None:
                continue

            for boundary in (
                getattr(
                    wall,
                    "ProvidesBoundaries",
                    None
                )
                or []
            ):

                space = getattr(
                    boundary,
                    "RelatingSpace",
                    None
                )

                if (
                    space is not None
                    and
                    space.is_a("IfcSpace")
                ):

                    spaces.append(
                        space
                    )

    return _unique_spaces(
        spaces
    )


def get_connected_spaces(door):

    # --------------------------------------------------------------
    # First: direct door boundaries
    # --------------------------------------------------------------

    spaces = _spaces_from_boundaries(
        door
    )

    if len(spaces) >= 2:

        return spaces[:2]

    # --------------------------------------------------------------
    # Second: wall relationship
    # --------------------------------------------------------------

    wall_spaces = _spaces_from_wall(
        door
    )

    if len(wall_spaces) == 2:

        return wall_spaces

    return spaces


# ==========================================================================
# EXTERNAL DOOR DETECTION
# ==========================================================================

def is_external_door(door):

    # IFC external spatial element.
    for boundary in (
        getattr(
            door,
            "ProvidesBoundaries",
            None
        )
        or []
    ):

        space = getattr(
            boundary,
            "RelatingSpace",
            None
        )

        if (
            space is not None
            and
            space.is_a(
                "IfcExternalSpatialElement"
            )
        ):

            return True

    # Property-set fallback.
    try:

        psets = element.get_psets(
            door
        )

        common = psets.get(
            "Pset_DoorCommon",
            {}
        )

        value = common.get(
            "IsExternal"
        )

        if value is True:
            return True

        if str(value).lower() in (
            "true",
            "1",
            "yes"
        ):

            return True

    except Exception:
        pass

    # Name-based fallback.
    name = door_name(
        door
    ).lower()

    external_keywords = (
        "external",
        "exterior",
        "outside",
        "exit"
    )

    return any(
        key in name
        for key in external_keywords
    )


# ==========================================================================
# COLLECT DOOR LINKS
# ==========================================================================

def collect_door_links(model):

    """
    Create a list of usable door connections.

    Each result contains:

        door
        a
        b
        width
        capacity

    a/b are GlobalIds or OUTSIDE.
    """

    links = []
    skipped = []

    # --------------------------------------------------------------
    # Prepare all space geometries once.
    # --------------------------------------------------------------

    print(
        "\n[geo] Preparing space geometry..."
    )

    space_geometries = []

    for index, space in enumerate(
        model.by_type(
            "IfcSpace"
        )
    ):

        geo = _space_geo(
            space
        )

        if geo is not None:

            space_geometries.append(
                (
                    space,
                    geo
                )
            )

        if (
            index + 1
        ) % 25 == 0:

            print(
                f"[geo] Prepared "
                f"{index + 1}/"
                f"{len(model.by_type('IfcSpace'))} spaces"
            )

    print(
        f"[geo] Geometry available for "
        f"{len(space_geometries)} spaces"
    )

    doors = model.by_type(
        "IfcDoor"
    )

    # --------------------------------------------------------------
    # Process doors.
    # --------------------------------------------------------------

    print(
        f"\n[doors] Processing "
        f"{len(doors)} doors..."
    )

    for index, door in enumerate(
        doors
    ):

        connected = get_connected_spaces(
            door
        )

        a = None
        b = None

        # ----------------------------------------------------------
        # Direct IFC topology
        # ----------------------------------------------------------

        if len(connected) == 2:

            a = connected[0].GlobalId
            b = connected[1].GlobalId

        # ----------------------------------------------------------
        # One connected space + external door
        # ----------------------------------------------------------

        elif (
            len(connected) == 1
            and
            is_external_door(door)
        ):

            a = connected[0].GlobalId
            b = OUTSIDE

        # ----------------------------------------------------------
        # Geometry fallback
        # ----------------------------------------------------------

        else:

            try:

                geo_a, geo_b = geometric_door_spaces(
                    door,
                    space_geometries
                )

            except Exception as e:

                print(
                    f"[geo] Door matching failed for "
                    f"{door_name(door)}: {e}"
                )

                geo_a = None
                geo_b = None

            # Two spaces.
            if (
                geo_a is not None
                and
                geo_b is not None
                and
                geo_a.GlobalId
                !=
                geo_b.GlobalId
            ):

                a = geo_a.GlobalId
                b = geo_b.GlobalId

            # One space + exterior.
            elif (
                is_external_door(door)
                and
                (
                    geo_a is not None
                    or
                    geo_b is not None
                )
            ):

                space = (
                    geo_a
                    if geo_a is not None
                    else geo_b
                )

                a = space.GlobalId
                b = OUTSIDE

            # Existing single space + external.
            elif (
                len(connected) == 1
                and
                is_external_door(door)
            ):

                a = connected[0].GlobalId
                b = OUTSIDE

        # ----------------------------------------------------------
        # Could not connect.
        # ----------------------------------------------------------

        if a is None or b is None:

            skipped.append(
                (
                    door,
                    len(connected)
                )
            )

            continue

        # ----------------------------------------------------------
        # Door capacity.
        # ----------------------------------------------------------

        width = get_door_width(
            door
        )

        capacity = int(
            round(
                width
                *
                FLOW_COEFFICIENT
                *
                60
            )
        )

        links.append(
            {
                "door": door,
                "a": a,
                "b": b,
                "width": width,
                "capacity": capacity
            }
        )

        if (
            index + 1
        ) % 25 == 0:

            print(
                f"[doors] Processed "
                f"{index + 1}/{len(doors)}"
            )

    return links, skipped


# ==========================================================================
# DOOR ENTRY
# ==========================================================================

def _door_entry(link):

    return {
        "id": link["door"].GlobalId,
        "name": door_name(
            link["door"]
        ),
        "width": link["width"],
        "capacity": link["capacity"]
    }


# ==========================================================================
# DIAGNOSTICS
# ==========================================================================

def diagnose_model(
    model,
    links,
    skipped
):

    spaces = model.by_type(
        "IfcSpace"
    )

    doors = model.by_type(
        "IfcDoor"
    )

    boundaries = model.by_type(
        "IfcRelSpaceBoundary"
    )

    print(
        "\n"
        + "=" * 75
    )

    print(
        "IFC MODEL DIAGNOSTIC"
    )

    print(
        "=" * 75
    )

    print(
        f"IfcSpace:              {len(spaces)}"
    )

    print(
        f"IfcDoor:               {len(doors)}"
    )

    print(
        f"IfcRelSpaceBoundary:   {len(boundaries)}"
    )

    print(
        f"Usable door links:     {len(links)}"
    )

    print(
        f"Skipped doors:         {len(skipped)}"
    )

    print(
        "-" * 75
    )

    # --------------------------------------------------------------
    # Connectivity statistics
    # --------------------------------------------------------------

    internal = 0
    external = 0

    for link in links:

        if OUTSIDE in (
            link["a"],
            link["b"]
        ):

            external += 1

        else:

            internal += 1

    print(
        f"Internal door connections: {internal}"
    )

    print(
        f"External/exit connections: {external}"
    )

    print(
        "-" * 75
    )

    # --------------------------------------------------------------
    # Spaces
    # --------------------------------------------------------------

    print(
        "SPACES"
    )

    print(
        "-" * 75
    )

    for index, space in enumerate(
        spaces
    ):

        area = get_room_area(
            space
        )

        print(
            f"{index:3d} | "
            f"{space_name(space):40s} | "
            f"{area:10.2f} m2 | "
            f"{space.GlobalId}"
        )

    print(
        "-" * 75
    )

    # --------------------------------------------------------------
    # First skipped doors
    # --------------------------------------------------------------

    if skipped:

        print(
            "SKIPPED DOORS"
        )

        print(
            "-" * 75
        )

        for door, count in skipped[:30]:

            print(
                f"{door_name(door)} "
                f"| IFC spaces found = {count}"
            )

        if len(skipped) > 30:

            print(
                f"... plus "
                f"{len(skipped) - 30} more"
            )

    print(
        "=" * 75
    )


# ==========================================================================
# GRAPH NODES
# ==========================================================================

def _add_nodes(
    G,
    model,
    links
):

    for space in model.by_type(
        "IfcSpace"
    ):

        area = get_room_area(
            space
        )

        G.add_node(
            space.GlobalId,
            name=space_name(space),
            area=area,
            occupant_capacity=room_capacity(area)
        )

    # Add outside only when required.
    if any(
        OUTSIDE in (
            link["a"],
            link["b"]
        )
        for link in links
    ):

        G.add_node(
            OUTSIDE,
            name="OUTSIDE",
            area=0.0,
            occupant_capacity=0
        )


# ==========================================================================
# TOPOLOGY GRAPH
# ==========================================================================

def build_topology_graph(
    model,
    links
):

    G = nx.Graph()

    _add_nodes(
        G,
        model,
        links
    )

    for link in links:

        entry = _door_entry(
            link
        )

        a = link["a"]
        b = link["b"]

        if G.has_edge(
            a,
            b
        ):

            edge = G[a][b]

            edge["doors"].append(
                entry
            )

            edge["total_width"] += (
                link["width"]
            )

        else:

            G.add_edge(
                a,
                b,
                doors=[entry],
                total_width=link["width"],
                weight=1.0
            )

    print(
        f"[topology] nodes="
        f"{G.number_of_nodes()} "
        f"edges="
        f"{G.number_of_edges()}"
    )

    return G


# ==========================================================================
# FLOW GRAPH
# ==========================================================================

def build_flow_graph(
    model,
    links
):

    G = nx.DiGraph()

    _add_nodes(
        G,
        model,
        links
    )

    for link in links:

        entry = _door_entry(
            link
        )

        a = link["a"]
        b = link["b"]

        capacity = link[
            "capacity"
        ]

        # a -> b
        if G.has_edge(
            a,
            b
        ):

            G[a][b][
                "capacity"
            ] += capacity

            G[a][b][
                "doors"
            ].append(
                entry
            )

        else:

            G.add_edge(
                a,
                b,
                capacity=capacity,
                doors=[entry]
            )

        # b -> a
        if G.has_edge(
            b,
            a
        ):

            G[b][a][
                "capacity"
            ] += capacity

            G[b][a][
                "doors"
            ].append(
                entry
            )

        else:

            G.add_edge(
                b,
                a,
                capacity=capacity,
                doors=[entry]
            )

    print(
        f"[flow] nodes="
        f"{G.number_of_nodes()} "
        f"edges="
        f"{G.number_of_edges()}"
    )

    return G


# ==========================================================================
# NODE SELECTION
# ==========================================================================

def resolve_node(
    model,
    G,
    spec,
    label
):

    spaces = model.by_type(
        "IfcSpace"
    )

    # --------------------------------------------------------------
    # Integer index
    # --------------------------------------------------------------

    if isinstance(
        spec,
        int
    ):

        index = (
            spec + len(spaces)
            if spec < 0
            else spec
        )

        if not (
            0 <= index < len(spaces)
        ):

            raise IndexError(
                f"Invalid {label} index: "
                f"{spec}"
            )

        return spaces[
            index
        ].GlobalId

    # --------------------------------------------------------------
    # Text
    # --------------------------------------------------------------

    text = str(
        spec
    ).strip()

    if text.upper() == OUTSIDE:

        if OUTSIDE not in G:

            raise ValueError(
                "No exterior exit doors "
                "were detected."
            )

        return OUTSIDE

    # GlobalId.
    if text in G:

        return text

    # Name substring.
    matches = []

    for node, data in G.nodes(
        data=True
    ):

        name = str(
            data.get(
                "name",
                ""
            )
        )

        if (
            text.lower()
            in
            name.lower()
        ):

            matches.append(
                node
            )

    if not matches:

        raise ValueError(
            f"No space matches "
            f"{label} = '{text}'"
        )

    if len(matches) > 1:

        print(
            f"[!] {label} '{text}' "
            f"matches multiple spaces."
        )

        print(
            "    Using first match:"
        )

        print(
            f"    {G.nodes[matches[0]]['name']}"
        )

    return matches[0]


# ==========================================================================
# SHORTEST PATH
# ==========================================================================

def shortest_circulation_path(
    G,
    start,
    end
):

    try:

        path = nx.shortest_path(
            G,
            source=start,
            target=end,
            weight="weight"
        )

    except nx.NetworkXNoPath:

        print(
            "\n[!] No continuous "
            "circulation route."
        )

        return None

    except nx.NodeNotFound as e:

        print(
            f"\n[!] {e}"
        )

        return None

    print(
        "\n"
        + "=" * 75
    )

    print(
        "SHORTEST CIRCULATION PATH"
    )

    print(
        "=" * 75
    )

    print(
        f"Spaces visited: "
        f"{len(path)}"
    )

    print(
        f"Doors crossed: "
        f"{len(path) - 1}"
    )

    print()

    for i, node in enumerate(
        path
    ):

        print(
            f"{i + 1}. "
            f"{G.nodes[node]['name']}"
        )

        if i < len(path) - 1:

            next_node = path[
                i + 1
            ]

            doors = G[node][
                next_node
            ].get(
                "doors",
                []
            )

            if doors:

                print(
                    "     via: "
                    +
                    ", ".join(
                        d["name"]
                        for d in doors
                    )
                )

    print(
        "=" * 75
    )

    return path


# ==========================================================================
# MAX FLOW
# ==========================================================================

def _net_flows(
    flow_dict
):

    """
    Remove opposing flows so that the result represents
    net movement rather than simultaneous artificial reverse flow.
    """

    net = {}

    for u, edges in flow_dict.items():

        for v, flow in edges.items():

            if flow <= 0:
                continue

            reverse = (
                flow_dict
                .get(v, {})
                .get(u, 0)
            )

            if flow > reverse:

                net[
                    (u, v)
                ] = (
                    flow
                    -
                    reverse
                )

    return net


def analyse_max_flow(
    G,
    source,
    sink
):

    if source == sink:

        print(
            "[!] Start and end "
            "are the same."
        )

        return None

    try:

        value, flow_dict = nx.maximum_flow(
            G,
            source,
            sink,
            capacity="capacity"
        )

    except Exception as e:

        print(
            f"[!] Max-flow error: {e}"
        )

        return None

    net = _net_flows(
        flow_dict
    )

    print(
        "\n"
        + "=" * 75
    )

    print(
        "PEDESTRIAN FLOW ANALYSIS"
    )

    print(
        "=" * 75
    )

    print(
        f"From: "
        f"{G.nodes[source]['name']}"
    )

    print(
        f"To:   "
        f"{G.nodes[sink]['name']}"
    )

    print()

    print(
        f"Maximum sustainable flow: "
        f"{value} persons/min"
    )

    print()

    bottlenecks = []

    for (u, v), flow in net.items():

        capacity = G[u][v][
            "capacity"
        ]

        utilisation = (
            flow
            /
            capacity
            *
            100
            if capacity
            else 0
        )

        flag = ""

        if (
            utilisation
            >=
            BOTTLENECK_THRESHOLD
        ):

            flag = (
                " <-- BOTTLENECK"
            )

            bottlenecks.append(
                (
                    u,
                    v,
                    flow,
                    capacity,
                    utilisation
                )
            )

        print(
            f"{G.nodes[u]['name']} "
            f"-> "
            f"{G.nodes[v]['name']} | "
            f"{flow}/{capacity} p/min | "
            f"{utilisation:.1f}%"
            f"{flag}"
        )

    print(
        "\n"
        "BOTTLENECKS"
    )

    print(
        "-" * 75
    )

    if bottlenecks:

        for (
            u,
            v,
            flow,
            capacity,
            utilisation
        ) in bottlenecks:

            print(
                f"{G.nodes[u]['name']} "
                f"-> "
                f"{G.nodes[v]['name']} | "
                f"{flow}/{capacity} p/min | "
                f"{utilisation:.1f}%"
            )

    else:

        print(
            "None above "
            f"{BOTTLENECK_THRESHOLD:.0f}%."
        )

    print(
        "=" * 75
    )

    return value, net


# ==========================================================================
# ROOM REPORT
# ==========================================================================

def list_room_areas_and_capacities(
    model,
    sort_by="capacity"
):

    rows = []

    for space in model.by_type(
        "IfcSpace"
    ):

        area = get_room_area(
            space
        )

        rows.append(
            {
                "global_id":
                    space.GlobalId,

                "name":
                    space_name(space),

                "area_m2":
                    round(
                        area,
                        2
                    ),

                "capacity":
                    room_capacity(area),

                "area_known":
                    area > 0
            }
        )

    if sort_by == "area":

        rows.sort(
            key=lambda row:
            row["area_m2"],
            reverse=True
        )

    elif sort_by == "name":

        rows.sort(
            key=lambda row:
            row["name"]
        )

    else:

        rows.sort(
            key=lambda row:
            row["capacity"],
            reverse=True
        )

    print(
        "\n"
        + "=" * 75
    )

    print(
        "ROOM AREAS & OCCUPANT CAPACITIES"
    )

    print(
        "=" * 75
    )

    if not rows:

        print(
            "No IfcSpace elements found."
        )

        return rows

    width = max(
        20,
        max(
            len(row["name"])
            for row in rows
        )
    )

    header = (
        f"{'Room':<{width}} "
        f"{'Area (m2)':>12} "
        f"{'Capacity':>10}"
    )

    print(
        header
    )

    print(
        "-" * len(header)
    )

    for row in rows:

        note = ""

        if not row[
            "area_known"
        ]:

            note = (
                "  (estimated)"
            )

        print(
            f"{row['name']:<{width}} "
            f"{row['area_m2']:>12.2f} "
            f"{row['capacity']:>10}"
            f"{note}"
        )

    print(
        "-" * len(header)
    )

    total_area = sum(
        row["area_m2"]
        for row in rows
    )

    total_capacity = sum(
        row["capacity"]
        for row in rows
    )

    print(
        f"{'TOTAL':<{width}} "
        f"{total_area:>12.2f} "
        f"{total_capacity:>10}"
    )

    print(
        "=" * 75
    )

    return rows


# ==========================================================================
# DOOR REPORT
# ==========================================================================

def report_doors(
    G,
    links
):

    print(
        "\n"
        + "=" * 75
    )

    print(
        "DOOR CONNECTION REPORT"
    )

    print(
        "=" * 75
    )

    for link in links:

        a = link["a"]
        b = link["b"]

        name_a = (
            G.nodes[a]["name"]
            if a in G
            else a
        )

        name_b = (
            G.nodes[b]["name"]
            if b in G
            else b
        )

        print()

        print(
            f"Door: "
            f"{door_name(link['door'])}"
        )

        print(
            f"  Width: "
            f"{link['width']:.3f} m"
        )

        print(
            f"  Capacity: "
            f"{link['capacity']} p/min"
        )

        print(
            f"  Connection: "
            f"{name_a} <-> {name_b}"
        )

    print(
        "=" * 75
    )


# ==========================================================================
# CSV EXPORT
# ==========================================================================

def export_room_report_csv(
    rows,
    path=DEFAULT_CSV_PATH
):

    if not rows:

        print(
            "[report] No room rows to export."
        )

        return None

    try:

        with open(
            path,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=list(
                    rows[0].keys()
                )
            )

            writer.writeheader()

            writer.writerows(
                rows
            )

        print(
            f"[report] CSV written: "
            f"{os.path.abspath(path)}"
        )

        return path

    except Exception as e:

        print(
            f"[report] CSV failed: {e}"
        )

        return None


# ==========================================================================
# 2D NETWORK MAP
# ==========================================================================

def draw_node_door_map(
    G,
    output_path=DEFAULT_MAP_PATH
):

    try:

        import matplotlib

        matplotlib.use(
            "Agg"
        )

        import matplotlib.pyplot as plt

    except ImportError:

        print(
            "[map] matplotlib is not installed."
        )

        print(
            "[map] Skipping map."
        )

        return None

    if G.number_of_nodes() == 0:

        print(
            "[map] Graph is empty."
        )

        return None

    try:

        labels = {
            node:
            data["name"]
            for node, data
            in G.nodes(
                data=True
            )
        }

        node_sizes = []

        for node, data in G.nodes(
            data=True
        ):

            capacity = data.get(
                "occupant_capacity",
                0
            )

            size = min(
                300
                +
                10 * capacity,
                3000
            )

            node_sizes.append(
                size
            )

        edge_labels = {}

        for u, v, data in G.edges(
            data=True
        ):

            doors = data.get(
                "doors",
                []
            )

            if len(doors) == 1:

                label = doors[0][
                    "name"
                ]

            else:

                label = (
                    f"{len(doors)} doors"
                )

            edge_labels[
                (u, v)
            ] = label

        pos = nx.spring_layout(
            G,
            seed=42,
            k=1.5
        )

        plt.figure(
            figsize=(16, 12)
        )

        nx.draw_networkx_nodes(
            G,
            pos,
            node_size=node_sizes,
            node_color="#8ecae6",
            edgecolors="#023047",
            linewidths=1.5
        )

        nx.draw_networkx_edges(
            G,
            pos,
            width=2
        )

        nx.draw_networkx_labels(
            G,
            pos,
            labels=labels,
            font_size=8
        )

        nx.draw_networkx_edge_labels(
            G,
            pos,
            edge_labels=edge_labels,
            font_size=6
        )

        plt.title(
            "IFC Circulation Network"
        )

        plt.axis(
            "off"
        )

        plt.tight_layout()

        plt.savefig(
            output_path,
            dpi=150
        )

        plt.close()

        print(
            f"[map] Saved: "
            f"{os.path.abspath(output_path)}"
        )

        return output_path

    except Exception as e:

        print(
            f"[map] Failed: {e}"
        )

        return None


# ==========================================================================
# BLENDER / BONSAI HELPERS
# ==========================================================================

def _get_bim_tool():

    for module_name in (
        "bonsai.tool",
        "blenderbim.tool"
    ):

        try:

            return __import__(
                module_name,
                fromlist=["Ifc"]
            )

        except Exception:
            continue

    return None


def _object_center(
    tool,
    entity
):

    try:

        import mathutils

        obj = tool.Ifc.get_object(
            entity
        )

    except Exception:

        obj = None

    if obj is None:

        return None

    try:

        corners = [
            obj.matrix_world
            @
            mathutils.Vector(
                corner
            )
            for corner
            in obj.bound_box
        ]

        return (
            sum(
                corners,
                mathutils.Vector()
            )
            /
            len(corners)
        )

    except Exception:

        return None


# ==========================================================================
# FLOW COLOUR
# ==========================================================================

def _flow_color(
    utilisation
):

    t = max(
        0.0,
        min(
            1.0,
            utilisation / 100.0
        )
    )

    if t < 0.5:

        local = (
            t
            /
            0.5
        )

        return (
            local,
            1.0,
            0.0,
            1.0
        )

    local = (
        t - 0.5
    ) / 0.5

    return (
        1.0,
        1.0 - local,
        0.0,
        1.0
    )


# ==========================================================================
# BLENDER FLOW MATERIAL
# ==========================================================================

def _make_flow_material(
    name,
    color
):

    import bpy

    material = bpy.data.materials.get(
        name
    )

    if material is None:

        material = bpy.data.materials.new(
            name
        )

        material.use_nodes = True

    bsdf = (
        material.node_tree.nodes.get(
            "Principled BSDF"
        )
    )

    if bsdf:

        if "Base Color" in bsdf.inputs:

            bsdf.inputs[
                "Base Color"
            ].default_value = color

        if "Emission Color" in bsdf.inputs:

            bsdf.inputs[
                "Emission Color"
            ].default_value = color

        if "Emission Strength" in bsdf.inputs:

            bsdf.inputs[
                "Emission Strength"
            ].default_value = 0.5

    material.diffuse_color = color

    return material


# ==========================================================================
# BLENDER FLOW VISUALISATION
# ==========================================================================

def draw_flow_visualization(
    model,
    G,
    net_flow,
    collection_name="Circulation Flow",
    min_thickness=0.03,
    max_thickness=0.25
):

    try:

        import bpy

    except ImportError:

        print(
            "[viz] Blender bpy unavailable."
        )

        return

    tool = _get_bim_tool()

    if tool is None:

        print(
            "[viz] Bonsai / BlenderBIM unavailable."
        )

        return

    # --------------------------------------------------------------
    # Collection
    # --------------------------------------------------------------

    collection = bpy.data.collections.get(
        collection_name
    )

    if collection is None:

        collection = (
            bpy.data.collections.new(
                collection_name
            )
        )

        bpy.context.scene.collection.children.link(
            collection
        )

    # --------------------------------------------------------------
    # Remove old flow objects
    # --------------------------------------------------------------

    for obj in list(
        collection.objects
    ):

        data = obj.data

        bpy.data.objects.remove(
            obj,
            do_unlink=True
        )

        if (
            data is not None
            and
            data.users == 0
            and
            hasattr(
                data,
                "splines"
            )
        ):

            try:

                bpy.data.curves.remove(
                    data
                )

            except Exception:
                pass

    # --------------------------------------------------------------
    # Position cache
    # --------------------------------------------------------------

    position_cache = {}

    def get_position(
        global_id
    ):

        if global_id == OUTSIDE:

            return None

        if global_id not in position_cache:

            try:

                entity = model.by_guid(
                    global_id
                )

                position_cache[
                    global_id
                ] = _object_center(
                    tool,
                    entity
                )

            except Exception:

                position_cache[
                    global_id
                ] = None

        return position_cache[
            global_id
        ]

    # --------------------------------------------------------------
    # Maximum door capacity
    # --------------------------------------------------------------

    maximum_capacity = max(
        (
            door["capacity"]
            for _, _, edge
            in G.edges(
                data=True
            )
            for door
            in edge.get(
                "doors",
                []
            )
        ),
        default=1
    )

    maximum_capacity = max(
        maximum_capacity,
        1
    )

    drawn = 0

    # --------------------------------------------------------------
    # Draw
    # --------------------------------------------------------------

    for (
        u,
        v
    ), flow in net_flow.items():

        edge = G[u][v]

        edge_capacity = edge.get(
            "capacity",
            0
        )

        utilisation = (
            flow
            /
            edge_capacity
            *
            100
            if edge_capacity
            else 0
        )

        material = _make_flow_material(
            f"FlowMat_{round(utilisation / 5) * 5}",
            _flow_color(
                utilisation
            )
        )

        for door in edge.get(
            "doors",
            []
        ):

            p1 = get_position(
                u
            )

            p2 = get_position(
                v
            )

            pd = get_position(
                door["id"]
            )

            points = [
                p
                for p in (
                    p1,
                    pd,
                    p2
                )
                if p is not None
            ]

            if len(points) < 2:

                print(
                    f"[viz] Could not draw "
                    f"{door['name']}"
                )

                continue

            curve = bpy.data.curves.new(
                "flow_curve",
                "CURVE"
            )

            curve.dimensions = "3D"

            curve.fill_mode = "FULL"

            curve.bevel_depth = (
                min_thickness
                +
                (
                    max_thickness
                    -
                    min_thickness
                )
                *
                (
                    door["capacity"]
                    /
                    maximum_capacity
                )
            )

            spline = curve.splines.new(
                "POLY"
            )

            spline.points.add(
                len(points) - 1
            )

            for point, position in zip(
                spline.points,
                points
            ):

                point.co = (
                    position.x,
                    position.y,
                    position.z,
                    1.0
                )

            curve.materials.append(
                material
            )

            obj = bpy.data.objects.new(
                f"flow_{door['name']}_{utilisation:.0f}pct",
                curve
            )

            collection.objects.link(
                obj
            )

            drawn += 1

    print(
        f"[viz] Drew {drawn} flow curves "
        f"into '{collection_name}'"
    )


# ==========================================================================
# PRINT SPACE LIST
# ==========================================================================

def print_space_selection_list(
    model
):

    spaces = model.by_type(
        "IfcSpace"
    )

    print(
        "\n"
        + "=" * 75
    )

    print(
        "AVAILABLE SPACES"
    )

    print(
        "=" * 75
    )

    for index, space in enumerate(
        spaces
    ):

        print(
            f"{index:3d} | "
            f"{space_name(space)} | "
            f"{space.GlobalId}"
        )

    print(
        "=" * 75
    )


# ==========================================================================
# MAIN
# ==========================================================================

def main(
    ifc_path=None,
    start=0,
    end=-1,
    visualize=False,
    report=True,
    illustrate=True,
    door_report=True,
    csv_path=DEFAULT_CSV_PATH
):

    print(
        "\n"
        + "#" * 75
    )

    print(
        "# IFC CIRCULATION + PEDESTRIAN FLOW"
    )

    print(
        "#" * 75
    )

    # --------------------------------------------------------------
    # Load
    # --------------------------------------------------------------

    model = load_model(
        ifc_path
    )

    set_unit_scale(
        model
    )

    # --------------------------------------------------------------
    # Spaces
    # --------------------------------------------------------------

    spaces = model.by_type(
        "IfcSpace"
    )

    print(
        f"\n[model] Found "
        f"{len(spaces)} IfcSpace elements."
    )

    if len(spaces) < 2:

        print(
            "[!] At least two IfcSpace "
            "objects are required."
        )

        return None

    # --------------------------------------------------------------
    # Show spaces
    # --------------------------------------------------------------

    print_space_selection_list(
        model
    )

    # --------------------------------------------------------------
    # Door matching
    # --------------------------------------------------------------

    links, skipped = collect_door_links(
        model
    )

    # --------------------------------------------------------------
    # Diagnostic
    # --------------------------------------------------------------

    diagnose_model(
        model,
        links,
        skipped
    )

    # --------------------------------------------------------------
    # Build graphs
    # --------------------------------------------------------------

    topology_graph = build_topology_graph(
        model,
        links
    )

    flow_graph = build_flow_graph(
        model,
        links
    )

    # --------------------------------------------------------------
    # Resolve start/end
    # --------------------------------------------------------------

    try:

        start_id = resolve_node(
            model,
            topology_graph,
            start,
            "start"
        )

        end_id = resolve_node(
            model,
            topology_graph,
            end,
            "end"
        )

    except Exception as e:

        print(
            f"\n[!] Could not resolve "
            f"start/end: {e}"
        )

        print(
            "\nUse one of the indexes "
            "shown in AVAILABLE SPACES."
        )

        return None

    print(
        "\n"
        + "=" * 75
    )

    print(
        "SELECTED ROUTE"
    )

    print(
        "=" * 75
    )

    print(
        f"START: "
        f"{topology_graph.nodes[start_id]['name']}"
    )

    print(
        f"END:   "
        f"{topology_graph.nodes[end_id]['name']}"
    )

    print(
        "=" * 75
    )

    # --------------------------------------------------------------
    # Shortest route
    # --------------------------------------------------------------

    shortest_circulation_path(
        topology_graph,
        start_id,
        end_id
    )

    # --------------------------------------------------------------
    # Maximum flow
    # --------------------------------------------------------------

    flow_result = analyse_max_flow(
        flow_graph,
        start_id,
        end_id
    )

    # --------------------------------------------------------------
    # Door report
    # --------------------------------------------------------------

    if door_report:

        report_doors(
            topology_graph,
            links
        )

    # --------------------------------------------------------------
    # Room report
    # --------------------------------------------------------------

    rows = None

    if report:

        rows = list_room_areas_and_capacities(
            model
        )

        if csv_path:

            export_room_report_csv(
                rows,
                csv_path
            )

    # --------------------------------------------------------------
    # 2D topology map
    # --------------------------------------------------------------

    if illustrate:

        draw_node_door_map(
            topology_graph
        )

    # --------------------------------------------------------------
    # Blender flow visualization
    # --------------------------------------------------------------

    if (
        visualize
        and
        flow_result is not None
    ):

        _, net_flow = flow_result

        draw_flow_visualization(
            model,
            flow_graph,
            net_flow
        )

    # --------------------------------------------------------------
    # Complete
    # --------------------------------------------------------------

    print(
        "\n"
        + "#" * 75
    )

    print(
        "# ANALYSIS COMPLETE"
    )

    print(
        "#" * 75
    )

    return {
        "model":
            model,

        "topology_graph":
            topology_graph,

        "flow_graph":
            flow_graph,

        "links":
            links,

        "skipped_doors":
            skipped,

        "room_rows":
            rows,

        "flow_result":
            flow_result
    }


# ==========================================================================
# RUN
# ==========================================================================

if __name__ == "__main__":

    # --------------------------------------------------------------
    # When run from Blender's Text Editor:
    #
    # Simply run:
    #
    #     main()
    #
    # The active Bonsai IFC model is automatically used.
    # --------------------------------------------------------------

    main(
        ifc_path=None,

        # ----------------------------------------------------------
        # CHANGE THESE TWO VALUES
        # ----------------------------------------------------------

        start=0,
        end=-1,

        # ----------------------------------------------------------
        # OPTIONS
        # ----------------------------------------------------------

        visualize=False,
        report=True,
        illustrate=True,
        door_report=True,

        csv_path=DEFAULT_CSV_PATH
    )