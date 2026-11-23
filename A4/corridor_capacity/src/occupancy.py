"""Load BR18 reference values and estimate occupancy for individual IFC spaces."""

from decimal import Decimal
import json
import math
from pathlib import Path
import re

from ifcopenshell.util.element import get_predefined_type, get_pset
from ifcopenshell.util.unit import get_property_unit, get_unit_scale


# Project assumptions for Building 2608 labels, independent of the BR18 table.
ROOM_USE_BY_NAME = {
    "auditorium": "seated_assembly",
    "cafeteria": "seated_assembly",
    "cafetaria": "seated_assembly",
    "dinning area 1l": "seated_assembly",
    "dinning area 3l": "seated_assembly",
}
CHAIR_NAME = re.compile(r"^(?:(?:furniture|office|dining|desk)[\s_-]+)*(?:chair|stol)(?:$|[\s_-])", re.I)
# The Team 06 export models each fixed auditorium seat as one of these families.
FIXED_SEAT_FAMILIES = {"m_seating-auditorium", "m_seating-auditorium2"}
ROUTE_OR_SHAFT = re.compile(
    r"corridor(?: (?:gf|\d+l))?|exit stairs?(?: [a-z])?(?: (?:gf|\d+l))?|shaft(?: [a-z])?|lift"
)
REFERENCE_AREA = re.compile(r"area(?: (?:gf|[1-9]\d*l))?")
MEETING_ROOM_SEATS = re.compile(r"meeting room \((\d+)\)(?:\s.*)?")

CHAIR_ESTIMATE = "Modeled chair estimates"
BR18_ESTIMATE = "BR18 floor-area estimates"
REVIEW = "Needs review"
NON_ROOM_LOAD = "Circulation, shafts, and reference areas"


def load_reference():
    path = Path(__file__).resolve().parents[2] / "br18_reference.json"
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)


def count_chairs(space):
    chairs = set()
    for relationship in space.ContainsElements:
        for element in relationship.RelatedElements:
            if not element.is_a("IfcFurnishingElement"):
                continue
            predefined_type = get_predefined_type(element)
            family = (element.Name or "").partition(":")[0].strip()
            if predefined_type == "CHAIR" or (
                predefined_type in (None, "NOTDEFINED")
                and (CHAIR_NAME.match(family) or family.casefold() in FIXED_SEAT_FAMILIES)
            ):
                chairs.add(element.id())
    return len(chairs)


def floor_area_m2(model, space):
    for quantity_set in ("Qto_SpaceBaseQuantities", "BaseQuantities"):
        entry = get_pset(space, quantity_set, "NetFloorArea", verbose=True)
        if isinstance(entry, dict) and entry.get("class") == "IfcQuantityArea":
            quantity = model.by_id(entry["id"])
            unit = get_property_unit(quantity, model)
            if unit and unit.UnitType == "AREAUNIT":
                area = quantity.AreaValue * get_unit_scale(unit)
                if math.isfinite(area) and area > 0:
                    return area
    return None


def is_reference_area(space):
    name = " ".join((space.LongName or space.Name or "").split()).casefold()
    return bool((space.Name or "").casefold().startswith("area:") and REFERENCE_AREA.fullmatch(name))


def estimate_occupancy(model, space, densities, room_use=None):
    name = " ".join((space.LongName or space.Name or "").split()).casefold()
    if ROUTE_OR_SHAFT.fullmatch(name):
        return {"status": NON_ROOM_LOAD, "detail": "Circulation or shaft space. No separate room load assigned."}
    if is_reference_area(space):
        return {"status": NON_ROOM_LOAD, "detail": "Reference area record. No separate room load assigned."}

    chairs = count_chairs(space)
    if chairs:
        people = "person" if chairs == 1 else "people"
        furniture = "chair" if chairs == 1 else "chairs"
        detail = f"{chairs} {people} estimated from {chairs} modeled {furniture}"
        room_label = MEETING_ROOM_SEATS.fullmatch(name)
        if room_label and int(room_label[1]) != chairs:
            detail += f" | Verify seating. The room label says {room_label[1]}."
        return {"status": CHAIR_ESTIMATE, "people_min": chairs, "people_max": chairs, "detail": detail}

    category = room_use or ROOM_USE_BY_NAME.get(name)
    if category is None:
        return {"status": REVIEW, "detail": "No modeled chairs and no applicable BR18 use selected"}

    area = floor_area_m2(model, space)
    if area is None:
        return {"status": REVIEW, "detail": "No usable net floor area with an IFC area unit"}

    guidance = densities[category]
    min_density, max_density = guidance["people_per_m2"]
    area_for_estimate = Decimal(str(round(area, 6)))
    lower = math.ceil(area_for_estimate * min_density)
    upper = math.ceil(area_for_estimate * max_density)
    estimate = str(lower) if lower == upper else f"{lower}–{upper}"
    density = f"{min_density:g}" if min_density == max_density else f"{min_density:g}–{max_density:g}"
    classification = "selected use" if room_use else "use inferred from room name"
    detail = (
        f"{estimate} people estimated from {area:.2f} m² at {density} people/m² "
        f"[BR18: {guidance['use']}, {classification}]"
    )
    return {
        "status": BR18_ESTIMATE,
        "people_min": lower,
        "people_max": upper,
        "net_floor_area_m2": round(area, 6),
        "br18_use": category,
        "density_people_per_m2": [float(min_density), float(max_density)],
        "detail": detail,
    }


def occupancy_summary(model, space, densities, room_use):
    estimate = estimate_occupancy(model, space, densities, room_use)
    return estimate["status"], estimate["detail"]
