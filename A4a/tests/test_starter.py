import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from window_count.src.main import analyse
from runall import run_analyses, save_result


class StarterTests(unittest.TestCase):
    def test_runner_uses_python_settings_and_allows_argument_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capability = root / "capability"
            capability.mkdir()
            shutil.copy2(ROOT / "runall.py", capability / "runall.py")
            shutil.copytree(ROOT / "window_count", capability / "window_count",
                            ignore=shutil.ignore_patterns("__pycache__", "results"))
            source = capability / "building with spaces.ifc"
            model = ifcopenshell.file(schema="IFC4")
            model.create_entity("IfcWindow", GlobalId=ifcopenshell.guid.new())
            model.write(str(source))
            settings = capability / "settings.py"
            settings.write_text(f"MODEL_PATH = {source.name!r}\n", encoding="utf-8")
            command = [sys.executable, "-B", str(capability / "runall.py")]
            process = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            output = next((capability / "window_count" / "results").glob("run-*/result.json"))
            self.assertEqual(json.loads(output.read_text()), {"window_count": 1})
            settings.write_text("MODEL_PATH = ''\n", encoding="utf-8")
            failed = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Set MODEL_PATH", failed.stderr)
            override = subprocess.run(command + [str(source)], capture_output=True, text=True)
            self.assertEqual(override.returncode, 0, override.stderr)
            self.assertEqual(len(list((capability / "window_count" / "results").iterdir())), 2)

    def test_multiple_analyses_keep_results_separate_and_share_the_loaded_model(self):
        model = ifcopenshell.file(schema="IFC4")
        model.create_entity("IfcWindow", GlobalId=ifcopenshell.guid.new())
        received = []

        def second_analysis(input_model):
            received.append(input_model)
            return {"checked": True}

        with tempfile.TemporaryDirectory() as directory:
            with patch("runall.ANALYSES", {"window_count": analyse, "second": second_analysis}):
                run_analyses(model, directory)
            results = Path(directory)
            first = next((results / "window_count").glob("run-*/result.json"))
            second = next((results / "second").glob("run-*/result.json"))
            self.assertEqual(json.loads(first.read_text()), {"window_count": 1})
            self.assertEqual(json.loads(second.read_text()), {"checked": True})
            self.assertIs(received[0], model)

    def test_default_results_are_inside_each_analysis_folder(self):
        model = ifcopenshell.file(schema="IFC4")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("runall.__file__", str(root / "runall.py")):
                with patch("runall.ANALYSES", {"window_count": analyse, "second": analyse}):
                    run_analyses(model)
            for name in ("window_count", "second"):
                output = next((root / name / "results").glob("run-*/result.json"))
                self.assertEqual(json.loads(output.read_text()), {"window_count": 0})

    def test_analysis_accepts_a_model_and_distinguishes_zero(self):
        model = ifcopenshell.file(schema="IFC4")
        self.assertEqual(analyse(model), {"window_count": 0})
        model.create_entity("IfcWindow", GlobalId=ifcopenshell.guid.new())
        self.assertEqual(analyse(model), {"window_count": 1})

    def test_runner_preserves_input_and_previous_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example.ifc"
            model = ifcopenshell.file(schema="IFC4")
            model.create_entity("IfcWindow", GlobalId=ifcopenshell.guid.new())
            model.write(str(source))
            original = source.read_bytes()
            results = root / "results"
            for _ in range(2):
                process = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "runall.py"),
                     str(source), "--results-dir", str(results)],
                    capture_output=True, text=True,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertIn("Result saved to:", process.stdout)
            outputs = list(results.glob("window_count/run-*/result.json"))
            self.assertEqual(len(outputs), 2)
            for output in outputs:
                self.assertEqual(json.loads(output.read_text()), {"window_count": 1})
            self.assertEqual(source.read_bytes(), original)
            source.write_text("not an IFC", encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "runall.py"),
                 str(source), "--results-dir", str(results)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(len(list((results / "window_count").iterdir())), 2)

    def test_import_has_no_model_loading_or_output_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-B", "-c",
                 f"import sys; sys.path.insert(0, {str(ROOT)!r}); import window_count.src.main, runall"],
                cwd=directory, capture_output=True, text=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, "")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_result_is_not_written(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "results"
            for invalid in [object(), {"count": float("nan")}]:
                with self.assertRaises((TypeError, ValueError)):
                    save_result(invalid, results)
            self.assertFalse(results.exists())


if __name__ == "__main__":
    unittest.main()
