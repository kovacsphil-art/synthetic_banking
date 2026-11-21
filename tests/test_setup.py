"""Setup failures use temporary fabricated project trees, never workspace data."""

from pathlib import Path
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
import runpy
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.check_setup import ROOT, REQUIRED, check_layout, check_notebooks, check_demo_generator, check_packages, check_node


class SetupTests(unittest.TestCase):
    def test_complete_repository_interfaces_and_reviewed_generator(self):
        for check in (check_layout(ROOT), check_notebooks(ROOT), check_demo_generator(ROOT)):
            self.assertTrue(check.passed, check.message)

    def test_notebook_only_upload_reports_missing_supporting_files(self):
        with TemporaryDirectory() as directory:
            result = check_layout(directory)
            self.assertFalse(result.passed)
            self.assertIn("src/synthetic_banking/config.py", result.message)
            self.assertIn("scripts/Scotia Fake Records.py", result.message)

    def test_missing_and_escaping_bundle_notebooks_fail(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in REQUIRED:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            self.assertFalse(check_layout(root).passed)
            (root / "resources/synthetic_pipeline.job.yml").write_text("notebook_task:\n  notebook_path: ../../outside.py\n")
            self.assertFalse(check_layout(root).passed)

    def test_modified_fake_script_cannot_satisfy_pinned_policy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "src/synthetic_banking").mkdir(parents=True)
            shutil.copyfile(ROOT / "src/synthetic_banking/demo_export_policy.json", root / "src/synthetic_banking/demo_export_policy.json")
            (root / "scripts/Scotia Fake Records.py").write_text("# fabricated replacement\n")
            self.assertFalse(check_demo_generator(root).passed)

    def test_missing_and_malformed_notebooks_fail(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(check_notebooks(root).passed)
            (root / "notebooks").mkdir()
            (root / "notebooks/broken.ipynb").write_text("<<<<<<< unresolved conflict")
            self.assertFalse(check_notebooks(root).passed)

    def test_dependency_failure_has_actionable_message_without_exception_content(self):
        with patch("scripts.check_setup.importlib.import_module", side_effect=ImportError("private detail")):
            checks = check_packages()
        self.assertTrue(all(not c.passed for c in checks))
        self.assertTrue(all("requirements-dev.txt" in c.message for c in checks))
        self.assertTrue(all("private detail" not in c.message for c in checks))

    def test_missing_node_has_clear_remedy(self):
        with patch("scripts.check_setup.shutil.which", return_value=None):
            self.assertFalse(check_node().passed)

    @unittest.skipUnless(all(importlib.util.find_spec(n) for n in ("pandas", "openpyxl", "pyarrow")),
                         "Install requirements-dev.txt for the fabricated setup smoke test")
    def test_source_setup_wrapper_writes_six_linked_fabricated_inputs_at_configured_path(self):
        import pandas as pd
        policy = json.loads((ROOT / "src/synthetic_banking/demo_export_policy.json").read_text())
        with TemporaryDirectory() as directory:
            workbook = Path(directory) / "RCAR_source_column_list.xlsx"
            # Schema-only temporary workbook: no real source workbook or rows.
            with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
                for table, columns in policy["columns"].items():
                    columns = {c: t for c, t in columns.items() if c != "_UTILIZATION_RATE"}
                    pd.DataFrame({"Source Column": list(columns), "Data type": list(columns.values())}).to_excel(
                        writer, sheet_name=table, index=False,
                    )
            output = StringIO()
            with patch("synthetic_banking.config.SOURCE_DIR", directory), redirect_stdout(output):
                result = runpy.run_path(str(ROOT / "notebooks/00_Create_Fabricated_SOURCE.py"))
            self.assertEqual(set(result["saved_paths"]), set(policy["columns"]))
            frames = {table: pd.read_parquet(path) for table, path in result["saved_paths"].items()}
            self.assertEqual(len(frames["PERSON"]), policy["source_people"])
            result["fake_records"].validate_relationships(frames)
            for table, path in result["saved_paths"].items():
                self.assertEqual(Path(path).parent, Path(directory))
                self.assertIn(table + ":", output.getvalue())
            self.assertNotIn(frames["PERSON"]["PARTY_ID"].iloc[0], output.getvalue())


if __name__ == "__main__":
    unittest.main()
