"""Inspect IFC corridors, estimate room occupancy, or measure a route segment."""

import argparse
from collections import defaultdict
from pathlib import Path
import re
from textwrap import fill

import ifcopenshell


CORRIDOR_TERMS = ("corridor", "korridor", "gang", "gangareal", "fordelingsgang")


def space_label(space):
    label = space.LongName or space.Name or space.ObjectType or "Unnamed space"
    return " ".join(label.split())


def describe_space(space):
    return f"{space_label(space)} [{space.GlobalId}]"


def report_model(model, corridor_terms):
    spaces = model.by_type("IfcSpace")
    doors = model.by_type("IfcDoor")
    boundaries = model.by_type("IfcRelSpaceBoundary")
    furnishing = model.by_type("IfcFurnishingElement")

    # Match whole words to keep short labels such as 'gang' precise.
    alternatives = "|".join(re.escape(term) for term in corridor_terms)
    corridor_pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)
    corridors = [
        space
        for space in spaces
        if any(
            corridor_pattern.search(label or "")
            for label in (space.Name, space.LongName, space.ObjectType)
        )
    ]

    # Multiple boundary records can refer to the same space and door.
    door_spaces = defaultdict(set)
    for boundary in boundaries:
        element = boundary.RelatedBuildingElement
        space = boundary.RelatingSpace
        if element and element.is_a("IfcDoor") and space and space.is_a("IfcSpace"):
            door_spaces[element].add(space)

    paired_doors = {door: rooms for door, rooms in door_spaces.items() if len(rooms) == 2}

    print(f"IFC schema: {model.schema_identifier}")
    print(f"Spaces: {len(spaces)}")
    print(f"Corridor candidates by label: {len(corridors)}")
    print(f"Doors: {len(doors)}")
    print(f"Furnishing elements: {len(furnishing)}")
    print(f"Space boundaries: {len(boundaries)}")
    print(f"Doors referenced by two distinct spaces: {len(paired_doors)}")

    if not spaces:
        print("Review: no IfcSpace entities were found.")
    elif not corridors:
        print("Review: no space labels matched the corridor terms.")
    if not paired_doors:
        print("Review: direct door boundaries yielded no space pairs.")

    for corridor in sorted(corridors, key=describe_space):
        print(f"\nCorridor candidate: {describe_space(corridor)}")
        connections = [
            (door.GlobalId, describe_space(next(iter(rooms - {corridor}))))
            for door, rooms in paired_doors.items()
            if corridor in rooms
        ]
        if not connections:
            print("  No neighboring spaces identified from direct door boundaries.")
        for door_id, neighbor in sorted(connections):
            print(f"  Door {door_id} links to {neighbor}")

    print("\nCapacity result: not assessed. The output describes available IFC inputs.")


def report_occupancy(model, room, room_use):
    from corridor_capacity.src.occupancy import (
        BR18_ESTIMATE, CHAIR_ESTIMATE, NON_ROOM_LOAD, REVIEW, load_reference, occupancy_summary,
    )

    reference = load_reference()
    densities = reference["occupancy_densities"]
    if room_use and room_use not in densities:
        raise ValueError(f"Unknown BR18 use. Choose from: {', '.join(densities)}.")

    spaces = model.by_type("IfcSpace")
    if room:
        selection = " ".join(room.split())
        labels = selection.casefold()
        spaces = [
            space for space in spaces
            if selection == space.GlobalId or labels in {
                " ".join((label or "").split()).casefold()
                for label in (space.Name, space.LongName)
            }
        ]
        if len(spaces) != 1:
            raise ValueError("Use a unique IFC room name, room number, or GUID.")

    source = reference["occupancy_source"]
    print(f"Occupancy reference: {source['title']}, {source['version']}, {source['locator']}")
    print(source["url"])
    if not spaces:
        print("Review: no IfcSpace entities were found.")
        return

    results = defaultdict(list)
    for space in sorted(spaces, key=describe_space):
        status, detail = occupancy_summary(model, space, densities, room_use)
        if room:
            print(f"{describe_space(space)} | {status} | {detail}")
            return
        results[status].append((space, detail))

    print(f"\nOccupancy summary for {len(spaces)} IFC spaces")
    for status in (CHAIR_ESTIMATE, BR18_ESTIMATE, REVIEW, NON_ROOM_LOAD):
        print(f"  {status}: {len(results[status])}")

    for status in (CHAIR_ESTIMATE, BR18_ESTIMATE):
        if results[status]:
            print(f"\n{status}")
            for space, detail in results[status]:
                print(f"  {describe_space(space)}: {detail}")

    if results[REVIEW]:
        print(f"\n{REVIEW}")
        reasons = defaultdict(list)
        for space, detail in results[REVIEW]:
            reasons[detail].append(space_label(space))
        for reason, room_names in reasons.items():
            print(f"  {reason} ({len(room_names)})")
            print(fill(", ".join(room_names), width=100, initial_indent="    ", subsequent_indent="    "))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_path", type=Path, help="Path to a local IFC model")
    parser.add_argument(
        "--corridor-term", action="append", metavar="LABEL",
        help="Add a space label for corridor detection. Can be repeated.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--width-space", metavar="GUID", help="Measure a selected IfcSpace.")
    mode.add_argument(
        "--occupancy", nargs="?", const="", metavar="ROOM",
        help="Estimate occupancy for all spaces or for one room selected by name, number, or GUID.",
    )
    parser.add_argument(
        "--br18-use", metavar="USE",
        help="Select the BR18 room use for a single-room floor-area estimate.",
    )
    parser.add_argument(
        "--axis", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"),
        help="Start and end of a straight route in model X/Y coordinates, in metres.",
    )
    args = parser.parse_args()
    if bool(args.width_space) != bool(args.axis):
        parser.error("Use --width-space and --axis together.")
    if args.br18_use and not args.occupancy:
        parser.error("Use --br18-use with a room selected via --occupancy.")

    model_path = args.model_path.expanduser()
    if not model_path.is_file():
        parser.error(f"IFC model not found: {model_path}")

    try:
        model = ifcopenshell.open(model_path)
    except (ifcopenshell.Error, OSError, RuntimeError) as error:
        parser.exit(1, f"Could not open {model_path}: {error}\n")

    print(f"Model: {model_path.name}")
    if args.occupancy is not None:
        try:
            report_occupancy(model, args.occupancy, args.br18_use)
        except (OSError, ValueError) as error:
            parser.exit(1, f"Occupancy review required: {error}\n")
        return

    if args.width_space:
        from corridor_capacity.src.occupancy import load_reference
        from corridor_capacity.src.width import report_width

        try:
            space = model.by_guid(args.width_space)
            if space is None or not space.is_a("IfcSpace"):
                raise ValueError("The GUID must identify an IfcSpace.")
            print(f"Selected space: {describe_space(space)}")
            reference = load_reference()["common_access_width"]
            report_width(space, args.axis[:2], args.axis[2:], reference)
        except (OSError, RuntimeError, ValueError) as error:
            parser.exit(1, f"Width review required: {error}\n")
        return

    extra_terms = tuple(term.strip() for term in args.corridor_term or () if term.strip())
    report_model(model, CORRIDOR_TERMS + extra_terms)


if __name__ == "__main__":
    main()
