"""Publication safety checks use fabricated job metadata and the contract example."""

from copy import deepcopy
from io import BytesIO
import json
import hashlib
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
            dict(task_key=name, run_id=index + 100, end_time=2000, state=state.copy()) for index, name in enumerate(sorted(TASKS))])
        self.path = "/Volumes/public/reports/showcase/runs/20/latest-pipeline.json"
        self.output = dict(notebook_output=dict(result=json.dumps(dict(report_path=self.path, schema_version="2.0",
            report_sha256=hashlib.sha256(json.dumps(self.report).encode()).hexdigest()))))

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

    def test_optional_dependency_projection_is_bounded_and_closed(self):
        from synthetic_banking.validation_reporting import build_validation_report
        from test_sampling_fidelity import paired_profiles
        from synthetic_banking.fidelity import compare_profiles
        data = build_validation_report(compare_profiles("source", "generated", "generation", paired_profiles())["metrics"])
        self.report["validation_report"]["dependency_fidelity"] = data["dependency_fidelity"]
        validate_report(json.dumps(self.report).encode())
        for key, value in (("source_n", .5), ("conditional_tvd_pct", 101), ("unsupported_combination_rate", -1), ("PRIVATE_CATEGORY", "SECRET")):
            bad = deepcopy(self.report)
            bad["validation_report"]["dependency_fidelity"]["categorical"][0][key] = value
            with self.assertRaises(ValueError):
                validate_report(json.dumps(bad).encode())

    def test_no_successful_run_leaves_existing_publication_alone(self):
        self.run["state"]["result_state"] = "FAILED"
        self.assertIsNone(retrieve(self.client(), 10, "/Volumes/public/reports/showcase"))
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.outputs, [])

    def test_latest_selection_uses_validation_completion_not_run_start_or_reporting_repair(self):
        client = self.client()
        older_start = deepcopy(self.run)
        older_start.update(run_id=19, start_time=100, end_time=9000)
        newer_start = deepcopy(self.run)
        newer_start.update(run_id=20, start_time=200, end_time=10000)
        for task in older_start['tasks']:
            task['end_time'] = 8000
        for task in newer_start['tasks']:
            task['end_time'] = 7000
        # Newest-started/newest-reporting run is not the latest validated run.
        runs = {19:older_start,20:newer_start}
        client.jobs.list_runs = lambda **kw: [obj(newer_start),obj(older_start)]
        client.jobs.get_run = lambda **kw: obj(runs[kw['run_id']])
        self.path = '/Volumes/public/reports/showcase/runs/19/latest-pipeline.json'
        receipt=json.loads(self.output['notebook_output']['result']);receipt['report_path']=self.path
        self.output['notebook_output']['result']=json.dumps(receipt)
        report,run,_ = retrieve(client,10,'/Volumes/public/reports/showcase',with_receipt=True)
        self.assertEqual(run['run_id'],19);self.assertEqual(report,self.report)
        self.assertEqual(self.downloads,[self.path]);self.assertEqual(len(self.outputs),1)

    def test_automatic_selection_skips_incomplete_successes_but_cannot_guess_missing_validation_time(self):
        client=self.client();incomplete=deepcopy(self.run);incomplete['run_id']=21;incomplete['tasks'].pop()
        client.jobs.list_runs=lambda **kw:[obj(incomplete),obj(self.run)]
        client.jobs.get_run=lambda **kw:obj(incomplete if kw['run_id']==21 else self.run)
        self.assertEqual(retrieve(client,10,'/Volumes/public/reports/showcase'),self.report)
        next(t for t in self.run['tasks'] if t['task_key']=='validate').pop('end_time')
        self.downloads.clear();self.outputs.clear()
        with self.assertRaises(ValueError):retrieve(client,10,'/Volumes/public/reports/showcase')
        self.assertEqual(self.downloads,[]);self.assertEqual(self.outputs,[])

    def test_missing_or_invalid_checksums_stop_before_downloading_and_changed_bytes_fail(self):
        original=json.loads(self.output['notebook_output']['result'])
        for checksum in (None,'','not-a-checksum'):
            self.output['notebook_output']['result']=json.dumps({**original,'report_sha256':checksum})
            with self.assertRaises(ValueError):retrieve(self.client(),10,'/Volumes/public/reports/showcase',20)
            self.assertEqual(self.downloads,[])
        self.output['notebook_output']['result']=json.dumps({**original,'report_sha256':'0'*64})
        with self.assertRaisesRegex(ValueError,'checksum'):retrieve(self.client(),10,'/Volumes/public/reports/showcase',20)

    def test_invalid_explicit_ids_cannot_fall_back_to_automatic_selection(self):
        for run_id in (0,-1,True,'20'):
            client=self.client();client.jobs.list_runs=lambda **kw:self.fail('Invalid explicit IDs cannot select latest')
            with self.assertRaises(ValueError):retrieve(client,10,'/Volumes/public/reports/showcase',run_id)
            self.assertEqual(self.downloads,[])
        self.run['run_id']=21
        with self.assertRaises(ValueError):retrieve(self.client(),10,'/Volumes/public/reports/showcase',20)

    def test_postpilot_public_contract_is_closed_and_retains_review_state(self):
        report = json.loads((ROOT / "docs/reporting/example-postpilot.json").read_text())
        valid = validate_report(json.dumps(report).encode())
        self.assertEqual(valid['privacy']['status'], 'REVIEW_REQUIRED')
        self.assertFalse(valid['privacy']['row_level_downloads_enabled'])
        for mutate in (
            lambda r: r['privacy'].update(assessment_id='private-assessment'),
            lambda r: r['privacy'].update(row_level_downloads_enabled=True),
            lambda r: r['privacy']['near_matches'].update(source_records=[]),
            lambda r: r['validation_report']['post_pilot'].update(source_run_id='private-run'),
            lambda r: r['validation_report']['post_pilot']['numeric_details'][0].update(raw_values=[]),
            lambda r: r['privacy']['categorical_patterns'][0].update(label='private-category'),
        ):
            bad = deepcopy(report)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_report(json.dumps(bad).encode())

    def test_repaired_run_uses_only_latest_successful_reporting_attempt(self):
        task = next(t for t in self.run["tasks"] if t["task_key"] == "reporting")
        task.update(start_time=20, attempt_number=0, run_id=999)
        old = deepcopy(task)
        old.update(start_time=10, attempt_number=1, run_id=888,
                   state=dict(life_cycle_state="TERMINATED", result_state="FAILED"))
        self.run["tasks"].append(old)
        retrieve(self.client(), 10, "/Volumes/public/reports/showcase", 20)
        self.assertEqual(self.outputs, [dict(run_id=999)])
        self.assertEqual(self.downloads, [self.path])
        # A newer failed attempt must block, even with an older successful one.
        old.update(start_time=30)
        with self.assertRaises(ValueError): retrieve(self.client(), 10, "/Volumes/public/reports/showcase", 20)
        self.assertEqual(self.outputs, [])
        self.assertEqual(self.downloads, [])

    def test_ambiguous_or_undated_duplicate_attempts_cannot_publish(self):
        original = deepcopy(self.run)
        for start in (None, 10):
            self.run = deepcopy(original)
            task = self.run["tasks"][0]
            if start:
                task.update(start_time=start)
            self.run["tasks"].append(deepcopy(task))
            with self.assertRaises(ValueError): retrieve(self.client(), 10, "/Volumes/public/reports/showcase", 20)
            self.assertEqual(self.downloads, [])

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
                       {**self.report, "schema_version": "3.0"},
                       {**self.report, "pipeline_completed_at": "invalid"}):
            with self.assertRaises(ValueError): validate_report(json.dumps(report).encode())
        with self.assertRaises(ValueError): validate_report(b"x" * (1024 * 1024 + 1))
        with self.assertRaises(ValueError): validate_report(b'{"schema_version":"1.0","schema_version":"1.0"}')

    def test_free_text_warnings_are_replaced_before_publication(self):
        self.report["warnings"][0]["message"] = "PRIVATE_VALUE"
        report = validate_report(json.dumps(self.report).encode())
        self.assertNotIn("PRIVATE_VALUE", json.dumps(report))

    def test_legacy_reports_remain_valid_and_receipt_version_must_match(self):
        legacy=json.loads((ROOT / "docs/reporting/example-v1.json").read_text())
        self.assertEqual(validate_report(json.dumps(legacy).encode())["schema_version"], "1.0")
        self.output["notebook_output"]["result"]=json.dumps(dict(report_path=self.path,schema_version="1.0"))
        with self.assertRaises(ValueError): retrieve(self.client(),10,"/Volumes/public/reports/showcase",20)

    def test_demo_reference_requires_verified_task_and_matching_report_checksum(self):
        import hashlib
        self.report['demo_dataset']=dict(dataset_version='sage-demo-v123',release_mode='DEMO_ONLY',preview_sha256='a'*64)
        checksum=hashlib.sha256(json.dumps(self.report).encode()).hexdigest()
        receipt=dict(report_path=self.path,schema_version='2.0',report_sha256=checksum,demo_export_status='VERIFIED_DEMO_ONLY')
        self.output['notebook_output']['result']=json.dumps(receipt)
        self.assertEqual(retrieve(self.client(),10,'/Volumes/public/reports/showcase',20)['demo_dataset']['dataset_version'],'sage-demo-v123')
        for change in ({'report_sha256':'0'*64},{'demo_export_status':'DISABLED'},{'report_sha256':None}):
            self.output['notebook_output']['result']=json.dumps({**receipt,**change})
            with self.assertRaises(ValueError):retrieve(self.client(),10,'/Volumes/public/reports/showcase',20)
        self.output['notebook_output']['result']=json.dumps(receipt)
        self.run['tasks']=[t for t in self.run['tasks'] if t['task_key']!='demo_export_verification']
        with self.assertRaises(ValueError):retrieve(self.client(),10,'/Volumes/public/reports/showcase',20)

    def test_legacy_eight_task_aggregate_run_still_publishes_without_demo_files(self):
        self.run['tasks']=[t for t in self.run['tasks'] if t['task_key']!='demo_export_verification']
        report=retrieve(self.client(),10,'/Volumes/public/reports/showcase',20)
        self.assertNotIn('demo_dataset',report)
        self.assertEqual(self.downloads,[self.path])

    def test_private_nested_validation_fields_and_labels_cannot_be_published(self):
        for field in ("secret", "label"):
            report=deepcopy(self.report)
            report["validation_report"]["assessments"][0][field]="PRIVATE_PARTY"
            with self.assertRaises(ValueError): validate_report(json.dumps(report).encode())

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
