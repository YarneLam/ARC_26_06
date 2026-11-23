def analyse(model):
    """Return the course starter's IFC window count."""
    return {"window_count": len(model.by_type("IfcWindow"))}
