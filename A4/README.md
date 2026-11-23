# A4 | Corridor capacity screening for Building 2608

ARCH06 · Architecture · OpenBIM Analysts

## Claim and design stage

Our A2 use case asks whether the proposed corridors can serve the expected occupancy of the connected rooms. The runner screens every identified corridor space across all storeys of the architectural IFC. Stage C is the primary design stage for architecture and fire-safety coordination. Stage B can use the same method to compare layouts with equivalent IFC inputs and route assumptions. [A2 BPMN](https://github.com/YarneLam/ARC_26_06/blob/main/A2/IMG/ARCH06_A2.bpmn), [DTU Advanced Building Design stages](https://lifelonglearning.dtu.dk/en/civil-and-mechanical-engineering/single-course/advanced-building-design/)

## Run locally

From `A4/`, install dependencies and run the course template's local runner. The default IFC path in [settings.py](settings.py) is relative to this folder. Pass your own path as the first argument if your IFC is elsewhere.

```powershell
python -m pip install -r requirements.txt
python runall.py
```

`runall.py` opens the IFC once. Each registered analysis writes a separate `result.json` to a new folder in its own `results/` directory. The corridor analysis also writes `corridor_capacity.xlsx` in the same run folder. `--results-dir` selects a different output root. To reproduce the worked Corridor 2L segment run, use `python runall.py --segment`. The existing `main.py` also supports standalone inventory, occupancy, and width diagnostics.

```powershell
python main.py '..\IFC\26-08-D-Arch - Copy.ifc' --occupancy
python main.py '..\IFC\26-08-D-Arch - Copy.ifc' --occupancy 'Multipurpose Space' --br18-use seated_assembly
```

## Analysis functions and inputs

| Module | Inputs and outputs |
| --- | --- |
| `corridor_capacity/src/building.py` | `analyse(model)` finds corridor spaces and produces per-corridor results and storey coverage. |
| `corridor_capacity/src/main.py` | Contains the shared capacity calculation and the optional selected-segment run. |
| `corridor_capacity/src/connections.py` | Reads door-to-space boundaries where available and uses door or opening geometry and same-storey floor footprints to infer connections. |
| `corridor_capacity/src/occupancy.py` | Counts individual chairs assigned to a room. If none are found, it uses a configured or inferred room use and the IFC `NetFloorArea` for a BR18 estimate. Independently documented loads can be entered with their source. |
| `corridor_capacity/src/width.py` | Samples cross-sections between facing footprint edges at intervals of at most 0.10 m, records the narrowest modeled section and reports its coordinates. |

Corridor detection uses `IfcSpace` labels such as `Corridor`, `Hallway`, `Circulation`, `Korridor` and `Gang`. Add GUIDs to `EXTRA_CORRIDOR_GUIDS` in [settings.py](settings.py) for corridor spaces with other labels. Every IFC storey appears in the coverage report. If a storey has no identified corridor space or a footprint cannot be measured, the report flags the gap.

The six available course IFCs contain zero `IfcRelSpaceBoundary` records. To infer adjacency, the tool samples points on opposite sides of the doorway, beyond the modeled opening or door footprint. It excludes whole-floor `Area:` references from room matching. The first matching space on each side must be unique for a link to qualify as inferred. Verify the inferred links and open passages against the relevant design plan. [IfcOpenShell geometry documentation](https://docs.ifcopenshell.org/ifcopenshell-python/geometry_processing.html)

The occupancy fallback multiplies net floor area by a sourced density and rounds up. The JSON records both ends of BR18 ranges. Each corridor sums each room once, including rooms with two doors. Configure `VERIFIED_CORRIDOR_ROOM_GUIDS` per corridor after confirming the same-storey room assignments. The default uses directly connected rooms. Cross-floor and upstream flows need their own routing analysis. A room can connect to multiple corridors, so adding the corridor loads together can double-count people. [BR18 Annex 4, Table 2.3.2, p. 19](https://www.bygningsreglementet.dk/media/4kwdmmqe/bilag-4-forsamlingslokaler-butik-mv-ver-12-20211029-a.pdf#page=19)

The comparison uses **1.30 m** as the common-access reference. It also reports a load-based screening scenario using **10 mm per person** where the Annex 4 guidance applies, subject to the 1.30 m reference. This uses modeled floor-space width. Clear door openings, obstructions, and the rest of the route require their own checks. [BR18 §56(2)](https://www.bygningsreglementet.dk/Tekniske-bestemmelser/02/Krav/55_56), [BR18 Annex 4, §2.3.3.2](https://www.bygningsreglementet.dk/media/4kwdmmqe/bilag-4-forsamlingslokaler-butik-mv-ver-12-20211029-a.pdf#page=19)

The Excel `Capacity` sheet shows the modeled width, reference width for the upper known load, and widening in whole millimetres for each corridor. It uses the modeled width before display rounding and rounds any positive shortfall up to the next millimetre. The yellow what-if inputs let you try another occupant load per corridor. `Storeys` shows coverage and `Room loads` lists the room estimates and any missing loads.

## Whole-IFC Team 08 run

The Part D IFC yielded four corridors across six storeys. The ground-floor footprint contained a potential **1200 mm** bottleneck, a **100 mm** shortfall against the **1300 mm** common-access reference. Hallway coverage on 4L and 5L needs review because the runner identified no corridor space on either storey. Verify the reported ground-floor bottleneck and route loads against the design plans.

| Corridor | Known occupants | Modeled width (mm) | Reference for known load (mm) | Widening (mm) |
| --- | ---: | ---: | ---: | ---: |
| GF | 16 | 1200 | 1300 | 100 |
| 1L | 92 | 3010 | 1300 | 0 |
| 2L | 250 | 2689 | 2500 | 0 |
| 3L | 88 | 2650 | 1300 | 0 |

The four known loads came from modeled seats. Eight connected room records lacked an occupancy estimate. The standalone Auditorium check estimated 232 people using the BR18 floor-area fallback. The doorway scan did not assign the Auditorium to a corridor in this run.

## Worked Corridor 2L run

On the Team 08 Part D export dated 23 June 2026, the narrowest modeled section was **2.942 m**. The tool inferred **17 door links** and flagged **one doorway** for review. It estimated **96 people** from the rooms with usable loads, giving a **1.30 m** reference for that known load. The result is `review_required` while the doorway, the toilet's occupant load, and the egress routing assumptions are open.

## Submission

The [input IDS](corridor_capacity.ids) accompanies the worked Corridor 2L example and checks its corridor label and storey, door identities, and the net floor area of the assembly room scenarios. The whole-model Python analysis assesses coverage and geometry for each IFC.

This runner follows the [course IFC template](https://github.com/timmcginley/node-comply-template). Keep the IFC, environment, and unreviewed runs local. Select an approved `result.json` and record the IFC revision, run settings, limitations, and code commit. Record its commit-specific GitHub link in the node-comply block’s Notes, save the block, and save the shared workspace. See [CHANGELOG.md](CHANGELOG.md) for changes to the analysis.
