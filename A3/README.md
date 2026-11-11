# Automated IFC Door Scheduling and Information Quality Checks

## Summary

Learn how to extract architectural door data from an IFC model, define project information requirements, check classifications and dimensions automatically, and export the results as an Excel quality report.

**Target audience:** OpenBIM Analyst – Level 3

**Focus area:** Architecture

## Learning Objectives

By completing this tutorial, participants will learn to:

- Extract door information using IfcOpenShell.
- Understand IFC classification references.
- Define project-specific information requirements.
- Perform automated quality checks.
- Export and interpret an Excel quality report.

## Requirements

- Python 3.11 or compatible version
- Jupyter Notebook
- IfcOpenShell
- Pandas
- openpyxl
- `26-01-D-ARCH.ifc` (provided in the course materials)

Basic Python knowledge is recommended.

## Getting Started

**1.** Place `tutorial.ipynb` and `26-01-D-ARCH.ifc` in the same folder.

**2.** Open Command Prompt in that folder and install the required packages:

```bash
python -m pip install ifcopenshell notebook pandas openpyxl
```

**3.** Start Jupyter Notebook:

```bash
jupyter notebook
```

**4.** Open `tutorial.ipynb` and run the code cells from top to bottom.

## Tutorial Overview

The notebook contains five steps:

1. **Load the IFC Model** – Identify the doors in the building.
2. **Extract Dimensions and Classifications** – Retrieve door properties and classification references.
3. **Define Information Requirements** – Set classification rules and door width limits.
4. **Automated Quality Checks** – Identify missing information and unusual dimensions.
5. **Export the Excel Report** – Generate a door schedule and quality reports.

## Expected Results

Using the original example settings, the model should produce:

| Result | Number |
|---|---:|
| Total doors | 130 |
| PASS | 12 |
| FAIL | 118 |
| Dimension Review | 1 |

These results are based on the example information requirements, not official building regulations.

## Practical Exercise

At the end of the notebook, participants change the minimum door width from 500 mm to 900 mm and rerun the quality checks.

They then compare the results and explain the difference between an information requirement failure and a dimension review warning.

## Output

The notebook generates `door_quality_report_final.xlsx`, containing three worksheets:

- **Door Schedule** – All doors and their extracted information.
- **Quality Issues** – Doors that fail the defined information requirements.
- **Dimension Review** – Doors with unusual or invalid recorded widths.