import json
from pathlib import Path
import sys
import unittest

import ifcopenshell
from ifcopenshell.guid import new

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corridor_capacity.src.main import analyse


def placement(model):
    point = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    return model.create_entity("IfcAxis2Placement3D", Location=point)


def rectangle(model, context, bounds, height):
    x1, y1, x2, y2 = bounds
    points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    curve = model.create_entity(
        "IfcPolyline", Points=[model.create_entity("IfcCartesianPoint", Coordinates=p) for p in points]
    )
    profile = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=curve)
    solid = model.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=profile, Position=placement(model), Depth=height,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
    )
    shape = model.create_entity(
        "IfcShapeRepresentation", ContextOfItems=context, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    return model.create_entity("IfcProductDefinitionShape", Representations=[shape])


def test_model():
    model = ifcopenshell.file(schema="IFC4")
    context = model.create_entity(
        "IfcGeometricRepresentationContext", ContextType="Model", CoordinateSpaceDimension=3,
        Precision=0.00001, WorldCoordinateSystem=placement(model),
    )
    length_unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    project = model.create_entity(
        "IfcProject", GlobalId=new(), RepresentationContexts=[context],
        UnitsInContext=model.create_entity("IfcUnitAssignment", Units=[length_unit]),
    )
    storey = model.create_entity("IfcBuildingStorey", GlobalId=new(), Name="Level 1")
    model.create_entity("IfcRelAggregates", GlobalId=new(), RelatingObject=project, RelatedObjects=[storey])
    corridor = model.create_entity(
        "IfcSpace", GlobalId=new(), LongName="Corridor", Representation=rectangle(model, context, (0., 0., 10., 2.), 3.),
    )
    room = model.create_entity(
        "IfcSpace", GlobalId=new(), LongName="Studio", Representation=rectangle(model, context, (0., 2.2, 10., 5.), 3.),
    )
    model.create_entity("IfcRelAggregates", GlobalId=new(), RelatingObject=storey, RelatedObjects=[corridor, room])

    doors = [
        model.create_entity("IfcDoor", GlobalId=new(), Representation=rectangle(model, context, bounds, 2.))
        for bounds in [(2., 2., 3., 2.2), (4., 2., 5., 2.2), (7., -.2, 8., 0.)]
    ]
    model.create_entity("IfcRelContainedInSpatialStructure", GlobalId=new(), RelatingStructure=storey, RelatedElements=doors)
    chairs = [model.create_entity("IfcFurniture", GlobalId=new(), PredefinedType="CHAIR") for _ in range(4)]
    model.create_entity("IfcRelContainedInSpatialStructure", GlobalId=new(), RelatingStructure=room, RelatedElements=chairs)
    return model, room


class CorridorCapacityTest(unittest.TestCase):
    def test_infers_door_pairs_and_counts_each_room_once(self):
        model, room = test_model()
        result = analyse(model, corridor_selector="Corridor", route_axis=((1., 1.), (9., 1.)))
        self.assertEqual(result["width"]["minimum_m"], 2.)
        self.assertEqual([door["status"] for door in result["connections"]["door_links"]],
                         ["inferred", "inferred", "needs_review"])
        self.assertEqual([record["room_guid"] for record in result["rooms"]], [room.GlobalId])
        self.assertEqual(result["capacity"]["known_room_load_people"], [4, 4])
        self.assertEqual(result["capacity"]["status"], "review_required")
        json.dumps(result, allow_nan=False)

    def test_uses_documented_load_for_a_verified_route(self):
        model, room = test_model()
        guid = room.GlobalId
        result = analyse(
            model, corridor_selector="Corridor", route_axis=((1., 1.), (9., 1.)),
            verified_route_rooms=(guid,), documented_loads={guid: {"people": 250, "source": "Test schedule"}},
        )
        self.assertEqual(result["capacity"]["required_width_for_known_load_m"], [2.5, 2.5])
        self.assertEqual(result["capacity"]["known_load_width_comparison"], "below_upper_reference")
        self.assertEqual(result["capacity"]["status"], "screening_complete")
