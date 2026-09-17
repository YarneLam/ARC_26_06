import bonsai.tool as tool
import ifcopenshell.util.element
from collections import defaultdict

model = tool.Ifc.get()

results = defaultdict(lambda: {
    "toilets": 0,
    "urinals": 0
})

total_toilets = 0
total_urinals = 0


for element in model.by_type("IfcFlowTerminal"):

    name = str(element.Name or "").lower()

    if "toilet" in name or "urinal" in name:

        container = ifcopenshell.util.element.get_container(element)

        if container:
            storey = container.Name or "Unknown"
        else:
            storey = "Unknown"

        if "toilet" in name:
            results[storey]["toilets"] += 1
            total_toilets += 1

        elif "urinal" in name:
            results[storey]["urinals"] += 1
            total_urinals += 1


total = total_toilets + total_urinals


print("\nSANITARY FACILITIES - BUILDING 308")
print("----------------------------------")

for storey, data in results.items():

    storey_total = data["toilets"] + data["urinals"]

    if total > 0:
        percentage = storey_total / total * 100
    else:
        percentage = 0

    print("\nStorey:", storey)
    print("Toilets:", data["toilets"])
    print("Urinals:", data["urinals"])
    print("Total:", storey_total)
    print("Percentage:", round(percentage, 1), "%")


print("\nBUILDING TOTAL")
print("Toilets:", total_toilets)
print("Urinals:", total_urinals)
print("Total:", total)