def analyse(model):
    """Return a starter window count, not a compliance assessment."""
    windows = model.by_type("IfcWindow")
    return {"window_count": len(windows)}
