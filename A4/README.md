# A4 | Corridor capacity screening for Building 2608

ARCH06 · Architecture · OpenBIM Analysts

## Claim and design stage

Our A2 use case asks whether the proposed corridors can serve the expected occupancy of the connected rooms. The worked check focuses on one straight segment of Corridor 2L in the Team 08 Part D architectural IFC. Stage C is the primary design stage for architecture and fire-safety coordination. Stage B can use the same method to compare layouts with equivalent IFC inputs and route assumptions. [A2 BPMN](https://github.com/YarneLam/ARC_26_06/blob/main/A2/IMG/ARCH06_A2.bpmn), [DTU Advanced Building Design stages](https://lifelonglearning.dtu.dk/en/civil-and-mechanical-engineering/single-course/advanced-building-design/)

## Run locally

From `A4/`, install dependencies and run the course template's local runner. The default IFC path in [settings.py](settings.py) is relative to this folder. Pass your own path as the first argument if your IFC is elsewhere.

```powershell
python -m pip install -r requirements.txt
python runall.py
python -m unittest discover -s tests
```

`runall.py` opens the IFC once. Each registered analysis writes a separate `result.json` to a new folder in its own `results/` directory. `--results-dir` selects a different output root. The existing `main.py` also supports standalone inventory, occupancy, and width diagnostics:

```powershell
python main.py '..\IFC\26-08-D-Arch - Copy.ifc' --occupancy
python main.py '..\IFC\26-08-D-Arch - Copy.ifc' --occupancy 'Multipurpose Space' --br18-use seated_assembly
```

## Analysis functions and inputs

| Module | Inputs and outputs |
| --- | --- |
| `corridor_capacity/src/main.py` | `analyse(model)` reads the selected `IfcSpace`, calls the analysis functions, and returns a JSON-compatible dictionary. |
| `corridor_capacity/src/connections.py` | Uses storey membership, `IfcSpace` floor footprints, and `IfcDoor` or `IfcOpeningElement` geometry to find the space on each side. It keeps the doors along the selected segment and records ambiguous or missing matches for review. |
| `corridor_capacity/src/occupancy.py` | Counts individual chairs assigned to a room. If none are found, it uses a configured or inferred room use and the IFC `NetFloorArea` for a BR18 estimate. Independently documented loads can be entered with their source. |
| `corridor_capacity/src/width.py` | Samples cross-sections of the corridor floor footprint at intervals of at most 0.10 m and records the narrowest section. |

The six available course IFCs contain zero `IfcRelSpaceBoundary` records. To infer adjacency, the tool samples points on opposite sides of the doorway, beyond the modeled opening or door footprint. It excludes whole-floor `Area:` references from room matching. The first matching space on each side must be unique for a link to qualify as inferred. Verify the inferred links and open passages against the relevant design plan. [IfcOpenShell geometry documentation](https://docs.ifcopenshell.org/ifcopenshell-python/geometry_processing.html)

The occupancy fallback multiplies net floor area by a sourced density and rounds up. For BR18 ranges, both ends are reported. The known load sums each room once, including rooms with two doors. Configure `VERIFIED_ROUTE_ROOM_GUIDS` after confirming the egress routes and how occupants are assigned to the segment. Until then, the screening uses inferred directly connected rooms. Cross-floor or upstream flows need to be assessed as part of a broader routing analysis. [BR18 Annex 4, Table 2.3.2, p. 19](https://www.bygningsreglementet.dk/media/4kwdmmqe/bilag-4-forsamlingslokaler-butik-mv-ver-12-20211029-a.pdf#page=19)

The comparison uses **1.30 m** as the common-access reference. It also reports a load-based screening scenario using **10 mm per person** where the Annex 4 guidance applies, subject to the 1.30 m reference. This uses modeled floor-space width. Clear door openings, obstructions, and the rest of the route require their own checks. [BR18 §56(2)](https://www.bygningsreglementet.dk/Tekniske-bestemmelser/02/Krav/55_56), [BR18 Annex 4, §2.3.3.2](https://www.bygningsreglementet.dk/media/4kwdmmqe/bilag-4-forsamlingslokaler-butik-mv-ver-12-20211029-a.pdf#page=19)

## Worked Corridor 2L run

On the Team 08 Part D export dated 23 June 2026, the narrowest modeled section was **2.942 m**. The tool inferred **17 door links** and flagged **one doorway** for review. It estimated **96 people** from the rooms with usable loads, giving a **1.30 m** reference for that known load. The result is `review_required` while the doorway, the toilet's occupant load, and the egress routing assumptions are open.

## Submission

The [input IDS](corridor_capacity.ids) checks the selected corridor label and storey, door identities, and the net floor area of the assembly room scenarios. The Python analysis checks the geometry and the reviewer verifies route connections.

This runner follows the [course IFC template](https://github.com/timmcginley/node-comply-template). Keep the IFC, environment, and unreviewed runs local. Select an approved `result.json` and record the IFC revision, run settings, limitations, and code commit. Record its commit-specific GitHub link in the node-comply block’s Notes, save the block, and save the shared workspace. See [CHANGELOG.md](CHANGELOG.md) for changes to the analysis.
