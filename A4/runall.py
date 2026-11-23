"""Local runner adapted from timmcginley/node-comply-template."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from corridor_capacity.src.main import analyse as analyse_corridor
from settings import MODEL_PATH
from window_count.src.main import analyse as count_windows


ANALYSES = {"window_count": count_windows, "corridor_capacity": analyse_corridor}


def save_result(result, results_dir):
    content = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(tempfile.mkdtemp(prefix=f"run-{timestamp}-", dir=results_dir))
    output = run_dir / "result.json"
    output.write_text(content + "\n", encoding="utf-8")
    return output


def run_analyses(model, results_dir=None):
    outputs = {}
    for name, analyse in ANALYSES.items():
        destination = (
            Path(__file__).resolve().parent / name / "results"
            if results_dir is None else Path(results_dir) / name
        )
        output = save_result(analyse(model), destination)
        print(f"{name}: Result saved to: {output.resolve()}")
        outputs[name] = output
    return outputs


def main():
    parser = argparse.ArgumentParser(description="Run the A4 analyses on a local IFC.")
    parser.add_argument("model", nargs="?", type=Path, help="IFC path. Defaults to MODEL_PATH in settings.py.")
    parser.add_argument("--results-dir", type=Path, help="Optional root folder for analysis outputs.")
    args = parser.parse_args()
    if args.model is None:
        if not MODEL_PATH.strip():
            parser.error("Set MODEL_PATH in settings.py or pass an IFC path.")
        args.model = Path(__file__).resolve().parent / MODEL_PATH
    if not args.model.is_file():
        parser.error(f"IFC file not found: {args.model}")

    import ifcopenshell

    try:
        model = ifcopenshell.open(args.model)
        run_analyses(model, args.results_dir)
    except (ifcopenshell.Error, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"A4 analysis failed: {error}\n")


if __name__ == "__main__":
    main()
