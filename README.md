# A1 - Forensic BIM

## Group
Group 6

## Focus area
Architecture

## Claim
The report states that the existing toilet facilities are not well distributed throughout the building.

For this assignment, we focused on checking the distribution of toilets and urinals in the existing Building 308 IFC model.

## Source
Report: 26-09-A-ClientReport-Anon.pdf  
Section: 3.1 - Findings from the Existing Building  
Page: 3

## Method
We used Python, IfcOpenShell and Bonsai to search the IFC model.

The script searches for toilets and urinals stored as IfcFlowTerminal objects. It then finds which building storey each object belongs to and counts the number of fixtures on each floor.

## Results
The IFC model contains:
- 10 toilets
- 4 urinals
- 14 sanitary fixtures in total

The fixtures are distributed as follows:
- ES_Stue: 9 toilets and 4 urinals = 13 fixtures
- E1_1. sal: 1 toilet = 1 fixture

This means that 92.9% of the identified fixtures are located on ES_Stue and 7.1% are located on E1_1. sal.

## Identified issues
### Design issue
The toilet facilities are unevenly distributed between the two storeys.

13 out of 14 identified fixtures are located on ES_Stue, while only one toilet is located on E1_1. sal.

The IFC analysis supports the part of the report stating that the existing toilet facilities are not well distributed throughout the building.

The analysis does not determine whether there are too few toilets in total, since this would require information about the number of users and relevant requirements.

### Modelling issue
We first tried to identify the toilet rooms using IfcSpace.

The model only contains three IfcSpace objects, and they are named "Area". Because of this, the toilet rooms could not be identified from the spaces.

Instead, the toilets and urinals were identified as IfcFlowTerminal objects.

### Tool issue
The script identifies toilets and urinals based on their object names.

This means that an object could be missed if a different naming convention is used.

## Possible solutions
### Design
The toilet facilities could be distributed more evenly between the different floors of the building.

### Modelling
Rooms could be modelled as IfcSpace objects with clear names and functions, such as WC, office, corridor or classroom.

### Tool
The script could be improved by checking IFC type information, properties or classifications instead of only using the object name.