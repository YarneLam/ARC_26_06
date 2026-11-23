"""Populate the whole-IFC Excel report from the structured analysis result."""

from collections import Counter
from copy import deepcopy
import re
from xml.etree import ElementTree as ET

from .excel_report import MM_PER_METRE, set_value, tag


def corridor_labels(corridors):
    names = Counter((row["storey"], row["corridor"]) for row in corridors)
    result = {}
    for row in corridors:
        name = row["corridor"]
        guid = row["corridor_guid"]
        if names[row["storey"], name] > 1:
            name = f"{name} ({row['space_number'] or guid[-6:]})"
        result[guid] = name
    return result


def table_sheet(raw_xml, records, inputs, last_column):
    sheet = ET.fromstring(raw_xml)
    data = sheet.find(tag("sheetData"))
    rows = {int(row.attrib["r"]): row for row in data.findall(tag("row"))}
    for (column, index), value in inputs.items():
        set_value(rows[index], column, value)

    first_row = 9
    prototype = rows[first_row]
    data.remove(prototype)
    for index, fields in enumerate(records, start=first_row):
        row = deepcopy(prototype)
        row.set("r", str(index))
        for cell in row.findall(tag("c")):
            column = cell.attrib["r"].rstrip("0123456789")
            cell.set("r", f"{column}{index}")
            formula = cell.find(tag("f"))
            if formula is not None:
                formula.text = re.sub(r"(?<![$\w])([A-Z]+)9(?!\d)", rf"\g<1>{index}", formula.text)
        for column, value in fields.items():
            set_value(row, column, value)
        data.append(row)

    last_row = first_row + len(records) - 1
    dimension = sheet.find(tag("dimension"))
    if dimension is not None:
        dimension.set("ref", f"A1:{last_column}{last_row}")
    for conditional in sheet.findall(tag("conditionalFormatting")):
        conditional.set("sqref", re.sub(
            r"\b([A-Z]+)9(?::\1\d+)?\b", rf"\g<1>9:\g<1>{max(first_row, last_row)}", conditional.attrib["sqref"],
        ))
    return ET.tostring(sheet, encoding="utf-8", xml_declaration=True)


def render_capacity(raw_xml, result):
    corridors = result["corridors"]
    labels = corridor_labels(corridors)
    records = []
    for corridor in corridors:
        width = corridor["width"]["minimum_m"]
        capacity = corridor["capacity"]
        people = capacity["known_room_load_people"]
        records.append({
            "B": corridor["storey"], "C": labels[corridor["corridor_guid"]],
            "D": people[1] if people is not None else None,
            "E": width * MM_PER_METRE if width is not None else None,
            "I": "Screening complete" if capacity["status"] == "screening_complete" else "Review required",
        })
    reference = result["references"]
    inputs = {
        ("B", 3): f"{result['model']['ifc_header_name']}. {len(result['storeys'])} storeys, {len(corridors)} corridors identified.",
        ("D", 4): reference["common_access_width"]["minimum_m"] * MM_PER_METRE,
        ("H", 4): reference["assembly_route_width"]["metres_per_person"] * MM_PER_METRE,
    }
    return table_sheet(raw_xml, records, inputs, "L")


def render_storeys(raw_xml, result):
    records = [dict(zip("BCDEFGHI", (
        storey["storey"], storey["space_count"], storey["door_count"], storey["corridors_found"],
        storey["corridors_with_width"],
        len(storey["unlocated_door_guids"]) if storey["corridors_found"] else None,
        len(storey["spaces_without_usable_footprint"]) if storey["corridors_found"] else None,
        storey["coverage_status"],
    ))) for storey in result["storeys"]]
    reference = result["references"]
    inputs = {
        ("D", 3): reference["common_access_width"]["url"],
        ("D", 4): reference["assembly_route_width"]["url"],
        ("D", 5): len(result["corridors_without_storey_guids"]),
        ("D", 6): len(result["doors_without_storey_guids"]),
    }
    return table_sheet(raw_xml, records, inputs, "I")


def render_rooms(raw_xml, result):
    labels = corridor_labels(result["corridors"])
    records = []
    for corridor in result["corridors"]:
        for room in corridor["rooms"]:
            note = room.get("source") or room.get("detail") or ""
            if room["status"] == "Modeled chair estimates":
                _, _, note = note.partition(" | ")
            records.append(dict(zip("BCDEFGHI", (
                corridor["storey"], labels[corridor["corridor_guid"]], room["room"], room["status"],
                room.get("people_min"), room.get("people_max"),
                "Yes" if room["appears_in_multiple_corridors"] else "", note,
            ))))
    return table_sheet(raw_xml, records, {}, "I")


SHEETS = {
    "xl/worksheets/sheet1.xml": render_capacity,
    "xl/worksheets/sheet2.xml": render_storeys,
    "xl/worksheets/sheet3.xml": render_rooms,
}
