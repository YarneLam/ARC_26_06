# Changelog

## 2026-11-23

- Registered the corridor-capacity analysis in the course template's local runner.
- Split doorway matching, occupancy, width, and capacity screening into reusable functions.
- Added JSON output with inferred links, BR18 sources, room loads, and review status.
- Used Team 08 Corridor 2L for the worked segment example.
- Added the input IDS.
- Added a corridor capacity Excel report with the width shortfall in millimetres and an editable what-if occupant load.
- Made the whole IFC the default corridor-capacity scope. The reports include each identified corridor, storey coverage, connected room estimates, and the widening shortfall in millimetres.
- Kept the worked Corridor 2L segment available through `--segment`.
- Updated the IDS for whole-IFC inputs and labeled the Annex 4 width comparison as a screening scenario in the reports.
