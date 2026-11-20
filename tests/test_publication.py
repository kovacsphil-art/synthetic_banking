"""Publication safety checks use fabricated job metadata and the contract example."""

from copy import deepcopy
from io import BytesIO
import json
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from scripts.publish_showcase import TASKS, ROOT, report_path, retrieve, save_report, validate_report


def obj(value):
    return SimpleNamespace(**value, as_dict=lambda: deepcopy(value))


@unittest.skipUnless(importlib.util.find_spec("jsonschema"), "Install jsonschema==4.23.0 for publication tests")
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / "docs/reporting/example.json").read_text())
        state = dict(life_cycle_state="TERMINATED", result_state="SUCCESS")
        self.run = dict(job_id=10, run_id=20, state=state, tasks=[
            dict(task_key=name, run_id=index + 100, state=state.copy()) for index, name in enumerate(sorted(TASKS))])
        self.path = "/Volumes/public/reports/showcase/runs/20/latest-pipeline.json"
        self.output = dict(notebook_output=dict(result=json.dumps(dict(report_path=self.path, schema_version="1.0"))))

    def client(self):
        self.downloads = []
        self.outputs = []
        def download(path):
            self.downloads.append(path)
            return SimpleNamespace(contents=BytesIO(json.dumps(self.report).encode()))
        def get_output(**kwargs):
            self.outputs.append(kwargs)
            return obj(self.output)
        return SimpleNamespace(jobs=SimpleNamespace(get_run=lambda **kw: obj(self.run),
            list_runs=lambda **kw: [obj(self.run)], get_run_output=get_output), files=SimpleNamespace(download=download))

    def test_downloads_only_successful_execution_bound_report(self):
        result = retrieve(self.client(), 10, "/Volumes/public/reports/showcase")
        self.assertEqual(result, self.report)
        self.assertEqual(self.downloads, [self.path])
        task = next(t for t in self.run["tasks"] if t["task_key"] == "reporting")
        self.assertEqual(self.outputs, [dict(run_id=task["run_id"])])

    def test_no_successful_run_leaves_existing_publication_alone(self):
        self.run["state"]["result_state"] = "FAILED"
        self.assertIsNone(retrieve(self.client(), 10, "/Volumes/public/reports/showcase"))
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.outputs, [])

    def test_failures_and_wrong_jobs_never_download_or_read_task_outputs(self):
        original = deepcopy(self.run)
        for change in (lambda: self.run.update(job_id=99),
                       lambda: self.run["state"].update(result_state="FAILED"),
                       lambda: self.run["tasks"][0]["state"].update(result_state="FAILED"),
                       lambda: self.run["tasks"].pop()):
            self.run = deepcopy(original)
            change()
            client = self.client()
            with self.assertRaises(ValueError): retrieve(client, 10, "/Volumes/public/reports/showcase", 20)
            self.assertEqual(self.downloads, [])
            self.assertEqual(self.outputs, [])

    def test_missing_or_foreign_receipts_cannot_retrieve_latest_or_other_files(self):
        for path in ("/Volumes/public/reports/showcase/latest-pipeline.json",
                     "/Volumes/public/reports/showcase/runs/19/latest-pipeline.json",
                     "/Volumes/source/data/private.parquet"):
            self.output["notebook_output"]["result"] = json.dumps(dict(report_path=path, schema_version="1.0"))
            with self.assertRaises(ValueError): retrieve(self.client(), 10, "/Volumes/public/reports/showcase", 20)
            self.assertEqual(self.downloads, [])
        self.output = dict(notebook_output=dict(result="{}", truncated=True))
        with self.assertRaises(ValueError): report_path(self.run, self.output, 10, "/Volumes/public/reports/showcase")

    def test_unknown_private_fields_invalid_schema_and_oversize_are_rejected(self):
        for report in ({**self.report, "source_record": "PRIVATE"},
                       {**self.report, "schema_version": "2.0"},
                       {**self.report, "pipeline_completed_at": "invalid"}):
            with self.assertRaises(ValueError): validate_report(json.dumps(report).encode())
        with self.assertRaises(ValueError): validate_report(b"x" * (1024 * 1024 + 1))
        with self.assertRaises(ValueError): validate_report(b'{"schema_version":"1.0","schema_version":"1.0"}')

    def test_free_text_warnings_are_replaced_before_publication(self):
        self.report["warnings"][0]["message"] = "PRIVATE_VALUE"
        report = validate_report(json.dumps(self.report).encode())
        self.assertNotIn("PRIVATE_VALUE", json.dumps(report))

    def test_older_report_and_invalid_existing_report_cannot_be_overwritten(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "latest-pipeline.json"
            save_report(self.report, path)
            previous = path.read_bytes()
            older = {**self.report, "pipeline_completed_at": "2025-01-01T12:00:00Z"}
            with self.assertRaises(ValueError): save_report(older, path)
            self.assertEqual(path.read_bytes(), previous)
            path.write_text("invalid")
            with self.assertRaises(ValueError): save_report(self.report, path)
            self.assertEqual(path.read_text(), "invalid")


if __name__ == "__main__":
    unittest.main()
