"""Local model path and the project scenario passed to the A4 analysis."""

MODEL_PATH = "../IFC/26-08-D-Arch - Copy.ifc"
CORRIDOR_LABEL = "Corridor 2L"
ROUTE_AXIS_M = ((6.164193, 6.480951), (59.717259, -9.891864))

# Add IFC space GUIDs here when a corridor is modeled with a project-specific name.
EXTRA_CORRIDOR_GUIDS = ()

# Whole-model egress room assignments keyed by corridor IFC space GUID.
VERIFIED_CORRIDOR_ROOM_GUIDS = {}

# Set GUIDs here only after verifying each room's route on the design plan.
# An empty tuple uses rooms inferred to open directly onto the selected segment.
VERIFIED_ROUTE_ROOM_GUIDS = ()

# Optional use assignments keyed by IfcSpace GUID for rooms without modeled seats.
BR18_ROOM_USE = {}

# For a room with independently documented occupancy, supply a nonnegative
# integer `people` and a `source` (for example, a reviewed seating schedule).
DOCUMENTED_ROOM_LOADS = {}
