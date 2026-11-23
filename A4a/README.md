# Week 11 IFC starter

A minimal extension of the course's
[Working Together example](https://github.com/timmcginley/41934/blob/main/Activities/workingTogether.md).
Start coding now; output definitions can develop after your team discussion.
This starter does not execute in node-comply or replace the Speckle template.

## Copy into your repository

Copy this whole folder into your existing repository as
`A4`. Open a terminal in that copied folder.
Use your course-supported Python installation with IfcOpenShell support.
The starter was validated on Windows with Python 3.14 and the pinned
IfcOpenShell 0.9.0.post1 dependency.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Edit [settings.py](settings.py) once to point to your local IFC:

```python
MODEL_PATH = r"C:\Users\Student\Downloads\building.ifc"
```

Keep the `r` before the quotes so Windows backslashes work as written.
Then run without typing the path each time:

```powershell
.\.venv\Scripts\python.exe runall.py
```

The runner imports this setting; your reusable analysis stays in its own folder.
Relative settings paths are resolved from the A4 folder.
You can still override the setting for one run by passing a quoted IFC path
after `runall.py`. Avoid committing personal paths when sharing your code.

If `python` selects the wrong
installation on Windows, use the Python launcher (`py`) to create the environment.
Do not upload private models. The source IFC is opened for reading; the runner
does not write it back.

## Edit the analysis, not the runner

Edit [window_count/src/main.py](window_count/src/main.py).
The starting `analyse(model)` counts
`IfcWindow` instances and returns a dictionary:

```json
{"window_count": 12}
```

Zero means that the opened model contains no `IfcWindow` instances; it does not
prove that a building has no physical windows. The example makes no compliance
assessment. Missing files, unreadable IFCs and execution failures are errors,
not substitute results.

The function receives a real IfcOpenShell model, so normal IFC interrogation
works. Do not modify the supplied model unless explicitly agreed. Return
JSON-compatible values: dictionaries with string keys, lists, strings, finite
numbers, booleans or `None`. Convert IFC entities to agreed properties and
GlobalIds when exporting; do not return IFC objects directly.

If a later function needs further IFC interrogation, it can use the original
model and resolve GlobalIds. JSON records are not IfcOpenShell entities.
Other functions may accept datasets instead; not every function needs a model.

## Inspect and share deliberately

Each successful analysis writes
`<analysis-name>/results/run-<UTC-time>-<unique-suffix>/result.json`.
Earlier results are not overwritten. If writing fails, an incomplete folder may
remain; only a successful terminal message confirms that the result was written.
New runs are local experiments, not automatic deliveries to another team.
The optional `--results-dir <folder>` override instead writes to
`<folder>/<analysis-name>/run-.../result.json`. Existing results from older
layouts are left in place, not moved or deleted.

For now, select one result manually, record its model version, code commit,
settings and limitations, and share a commit-specific link to approved data.
Record that link in the canvas block's Notes. Save the block and then
**Save shared workspace**. Linking code does not execute it.

This starter intentionally has no automatic `run.json`, publishing pointer,
review workflow or GitHub discovery. Those can be added around the callable
function after reviewing the teams' agreed outputs. Keep selected results;
do not treat the folder timestamp as model/code provenance.

Before sharing meaningful updates, add a dated entry to
[CHANGELOG.md](CHANGELOG.md). Respect your repository's licence and acknowledge
the course example; this starter does not add a separate licence.

## Reuse the function

With the A4 folder on the Python import path, another script can import
`from window_count.src.main import analyse` and call `analyse(model)`. Importing it does not load a
model or write files. The runner is only the local entry point.

## Add another analysis

The shared runner loads the IFC once and passes it to each registered analysis.
Keep the model unchanged so one analysis does not affect another.

```text
A4/
  settings.py
  runall.py
  window_count/
    __init__.py
    src/
      __init__.py
      main.py
    results/
      run-.../
        result.json
```

Copy `window_count` to another clearly named folder (without copying its results)
and adapt its `src/main.py`. Import the new callable in `runall.py` and add its
folder name to `ANALYSES`, for example:

```python
from door_count.src.main import analyse as count_doors

ANALYSES = {
    "window_count": count_windows,
    "door_count": count_doors,
}
```

Keep the existing window import as well. Each registered analysis receives its
own results folder. The runner stops with an error if an analysis fails;
earlier successful outputs remain, so a partially completed run is not an
all-analysis success. Analyses are independent here: ordering in this dictionary
does not pass one result into another function.

## Check the starter

From this folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The tests create a tiny IFC, run the example twice, check separate analysis
outputs and check import-safe reuse.
Extend or replace the example test when you change the analysis.
