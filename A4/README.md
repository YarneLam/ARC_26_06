# A4 — Corridor capacity in Building 2608

ARCH06 · Architecture · OpenBIM Analysts

In A2 we asked whether the proposed corridors could serve the expected number of people in the rooms around them. For A4 we built a Python tool that uses the architectural IFC to check modeled corridor widths against estimated room loads. We would use it in Stage C, when the architects and fire-safety team can still change the layout or check an escape route in more detail. [A2 use case](../A2/README.md) · [A2 BPMN](../A2/IMG/ARCH06_A2.bpmn)

## What we found

We ran the tool on the Team 08 Part D IFC exported on 23 June 2026. It found four corridors across six storeys. The ground-floor footprint had a **1200 mm** section, **100 mm** below the **1300 mm** common-access reference. That is the first location we would check on the plan.

| Corridor | Known occupants | Modeled width (mm) | Screening reference (mm) | Width shortfall (mm) |
| --- | ---: | ---: | ---: | ---: |
| GF | 16 | 1200 | 1300 | 100 |
| 1L | 92 | 3010 | 1300 | 0 |
| 2L | 250 | 2689 | 2500 | 0 |
| 3L | 88 | 2650 | 1300 | 0 |

The tool identified no corridor spaces on 4L or 5L. The known loads came from modeled chairs, and eight of the rooms it linked had no usable estimate. The standalone BR18 check gave 232 people for the Auditorium, whose occupants are still unassigned in the corridor run. A width shortfall of zero only describes the known load and the modeled width. All four routes still need review.

We also tried the existing Building 308 IFC. It had three space records and no identifiable corridors, so that export gave us no baseline for a before-and-after comparison.

## How it works

1. We look for named corridor `IfcSpace` records on each storey, then sample widths across the modeled floor footprints.
2. We connect rooms to corridors through doors. The Team 08 IFC had no space boundaries, so the tool checks which room footprint lies on each side of the door opening. It flags ambiguous matches for review.
3. We count modeled chairs first. If a room has no chairs and we can match its use to a BR18 category, we use its net floor area and the density in [the BR18 reference file](br18_reference.json). Each directly connected room is counted once per corridor.
4. We compare the footprint width with the larger of the **1300 mm** common-access reference and the known load multiplied by **10 mm/person**. The second figure is an Annex 4 screening scenario. The designer still needs to check whether Annex 4 applies and whether the measured width is clear on the plan. [BR18 §56(2)](https://www.bygningsreglementet.dk/Tekniske-bestemmelser/02/Krav/55_56) · [BR18 Annex 4, §2.3.3.2 and Table 2.3.2](https://www.bygningsreglementet.dk/media/4kwdmmqe/bilag-4-forsamlingslokaler-butik-mv-ver-12-20211029-a.pdf#page=19)

The load covers rooms connected directly to a corridor. Routes through other corridors, stairs and open passages need to be traced on the egress plan. A room can appear under more than one corridor, so the per-corridor figures should be read individually.

## IFC inputs

The [IDS](corridor_capacity.ids) checks for spaces assigned to building storeys, door identifiers, and the type of any supplied `NetFloorArea` used for the fallback. The Python tool checks corridor labels, usable geometry, and room-to-door links. The IFC also needs either identifiable chairs or a usable area and room classification to estimate occupancy. Use [settings.py](settings.py) to add corridor GUIDs, verified room assignments, BR18 room uses, or documented loads.

## Run it

Open a terminal in the `A4` folder and pass the path to your local IFC.

```powershell
python -m pip install -r requirements.txt
python runall.py '..\IFC\26-08-D-Arch - Copy.ifc'
```

Open the new run folder in `corridor_capacity/results/`. It contains `corridor_capacity.xlsx` and `result.json`. In Excel, **Capacity** shows the comparison and has yellow cells for testing different loads. **Storeys** shows which levels were covered. **Room loads** shows where the occupant estimates came from. The JSON includes the doorway matches and the coordinates of each narrow section.

Use `--segment` to repeat the first test on a single stretch of Corridor 2L. The default command checks the whole IFC. The separate window count is the example analysis from the course starter.

## Sharing a run

The IFC and working runs are stored locally. When sharing a reviewed `result.json` in node-comply, record the model revision, code commit, settings and limits of the check. Put the commit-specific link to that result in the block’s Notes, then save the block and shared workspace. [Course A4 instructions](https://timmcginley.github.io/41934/Assignments/A4.html) · [Starter template](https://github.com/timmcginley/node-comply-template#inspect-and-share-deliberately)
