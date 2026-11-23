"""Populate the A4 Excel report template with the data from one IFC run."""

from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


TEMPLATE = Path(__file__).with_name("capacity_template.xlsx")
BUILDING_TEMPLATE = Path(__file__).with_name("building_template.xlsx")
MM_PER_METRE = 1000
XMLNS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", XMLNS)
ET.register_namespace("r", RELNS)


def tag(name):
    return f"{{{XMLNS}}}{name}"


def set_value(row, column, value):
    address = f"{column}{row.attrib['r']}"
    cell = row.find(f"{tag('c')}[@r='{address}']")
    if cell is None:
        cell = ET.SubElement(row, tag("c"), {"r": address})
        row[:] = sorted(row, key=lambda item: item.attrib["r"])

    del cell[:]
    cell.attrib.pop("t", None)
    if isinstance(value, str):
        cell.set("t", "inlineStr")
        text = ET.SubElement(ET.SubElement(cell, tag("is")), tag("t"))
        text.text = value
    elif value is not None:
        ET.SubElement(cell, tag("v")).text = str(value)


def render_run_data(raw_xml, result):
    sheet = ET.fromstring(raw_xml)
    data = sheet.find(tag("sheetData"))
    rows = {int(row.attrib["r"]): row for row in data.findall(tag("row"))}
    scenario = result["scenario"]
    model = result["model"]
    capacity = result["capacity"]
    links = result["connections"]["door_links"]
    low, high = capacity["known_room_load_people"] or (None, None)
    route_status = "Screening complete" if capacity["status"] == "screening_complete" else "Review required"
    assignment = "Verified room list" if scenario["room_assignment"] == "verified_room_list" else "Inferred direct rooms"
    inputs = (
        scenario["corridor"], scenario["storey"], model["ifc_header_name"],
        result["width"]["minimum_m"] * MM_PER_METRE, high,
        capacity["common_access_width_reference_m"] * MM_PER_METRE,
        capacity["annex_4_scenario_metres_per_person"] * MM_PER_METRE,
        route_status, sum(door["status"] == "needs_review" for door in links),
        len(capacity["rooms_missing_occupancy_guids"]), sum(door["status"] == "inferred" for door in links),
        assignment, low, model["ifc_export_timestamp"], result["width"]["station_m"],
    )
    for index, value in enumerate(inputs, start=4):
        set_value(rows[index], "C", value)
    set_value(rows[9], "G", result["references"]["common_access_width"]["url"])
    set_value(rows[10], "G", result["references"]["assembly_route_width"]["url"])

    # Repeat the styled room row for each source record without a fixed row limit.
    room_style = deepcopy(rows[22])
    data.remove(rows[22])
    for index, room in enumerate(result["rooms"], start=22):
        row = deepcopy(room_style)
        row.set("r", str(index))
        for cell in row.findall(tag("c")):
            column = cell.attrib["r"].rstrip("0123456789")
            cell.set("r", f"{column}{index}")
        note = room.get("source") or room.get("detail") or ""
        if room["status"] == "Modeled chair estimates":
            _, _, note = note.partition(" | ")
        fields = (
            room["room"], room["status"], room.get("people_min"), room.get("people_max"), room["room_guid"], note,
        )
        for column, value in zip("BCDEFG", fields):
            set_value(row, column, value)
        if len(note) > 64:
            row.set("ht", "30")
            row.set("customHeight", "1")
        data.append(row)

    dimension = sheet.find(tag("dimension"))
    if dimension is not None:
        dimension.set("ref", f"A1:G{21 + len(result['rooms'])}")
    return ET.tostring(sheet, encoding="utf-8", xml_declaration=True)


def calculate_on_open(raw_xml):
    workbook = ET.fromstring(raw_xml)
    calc = workbook.find(tag("calcPr"))
    if calc is None:
        calc = ET.SubElement(workbook, tag("calcPr"))
    calc.set("calcMode", "auto")
    calc.set("fullCalcOnLoad", "1")
    return ET.tostring(workbook, encoding="utf-8", xml_declaration=True)


def save_excel(result, destination):
    if result.get("scope") == "whole_ifc":
        from .building_excel import SHEETS

        template_path = BUILDING_TEMPLATE
        renderers = SHEETS
    else:
        template_path = TEMPLATE
        renderers = {"xl/worksheets/sheet2.xml": render_run_data}
    destination = Path(destination)
    temporary = destination.with_suffix(".tmp")
    try:
        with ZipFile(template_path) as template, ZipFile(temporary, "w") as output:
            for member in template.infolist():
                content = template.read(member)
                if member.filename in renderers:
                    content = renderers[member.filename](content, result)
                elif member.filename == "xl/workbook.xml":
                    content = calculate_on_open(content)
                output.writestr(member, content)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
