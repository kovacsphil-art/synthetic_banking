"""Validate the declared notebook interfaces and dynamic task references locally."""

import ast
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkflowWiringTests(unittest.TestCase):
    def test_job_is_serial_and_all_dynamic_outputs_have_defined_producers(self):
        text = (ROOT / "resources/synthetic_pipeline.job.yml").read_text()
        blocks = re.split(r"\n        - task_key: ", text)[1:]
        expected = ["source_profile", "llm_proposal", "approval_check", "synthetic_generation", "privacy_check", "generated_profile", "validate", "demo_export_verification", "reporting"]
        self.assertEqual([block.splitlines()[0] for block in blocks], expected)
        outputs = {
            "source_profile": {"source_run_id"}, "llm_proposal": {"source_run_id", "batch_id"},
            "approval_check": {"source_run_id", "batch_id", "approval_fingerprint"},
            "synthetic_generation": {"source_run_id", "batch_id", "generation_id"},
            "privacy_check": {"source_run_id", "batch_id", "generation_id", "privacy_assessment_id", "privacy_status", "row_level_release_allowed"},
            "generated_profile": {"source_run_id", "batch_id", "generation_id", "generated_run_id"},
            "validate": {"source_run_id", "batch_id", "generation_id", "generated_run_id", "validation_status", "validated_at"},
            "demo_export_verification": {"demo_export_status", "demo_dataset_version"},
        }
        self.assertIn("max_concurrent_runs: 1", text)
        for index, block in enumerate(blocks):
            key = expected[index]
            self.assertIn("max_retries: 0", block)
            if index:
                dependencies = re.findall(r"            - task_key: (\w+)", block)
                self.assertEqual(dependencies, [expected[index - 1]])
            for producer, field in re.findall(r"\{\{tasks\.(\w+)\.values\.(\w+)\}\}", block):
                self.assertLess(expected.index(producer), index)
                self.assertIn(field, outputs[producer], f"{key} references an unknown task value")
            path = re.search(r"notebook_path: (.+)", block).group(1)
            self.assertTrue((ROOT / "resources" / path).resolve().is_file())
        self.assertNotRegex(text, r"\bcurrent_run\b")
        self.assertRegex(text, r'name: demo_release_mode\s+default: DISABLED')
        # Avoid job parameters overriding the dynamically passed lineage keys.
        parameters = text.split("      tasks:")[0]
        for name in ("source_run_id", "batch_id", "generation_id", "generated_run_id"):
            self.assertNotRegex(parameters, rf"- name: {name}\s")

    def test_dataset_publication_has_separate_opt_in_and_pages_never_contains_full_files(self):
        text=(ROOT/'.github/workflows/publish-showcase.yml').read_text()
        self.assertIn('SAGE_PUBLISH_DEMO_DATASETS: ${{ vars.SAGE_PUBLISH_DEMO_DATASETS }}',text)
        self.assertIn("if: steps.report.outputs.demo_ready == 'true'",text)
        self.assertLess(text.index('- name: Check webpage contract'),text.index('- name: Publish only this execution'))
        staging=text.split('- name: Stage and check the exact public artifact')[1].split('- name: Check staged browser contract')[0]
        self.assertIn("steps.report.outputs.demo_ready",staging)
        self.assertIn('python scripts/stage_showcase.py',staging)
        self.assertNotRegex(staging,r'cp .*\.(csv|zip)')
        self.assertLess(text.index('- name: Stage and check'),text.index('- name: Commit only verified public'))
        commit=text.split('- name: Commit only verified public')[1].split('- uses: actions/upload-pages-artifact')[0]
        self.assertIn('git add -- docs/latest-pipeline.json',commit)
        self.assertIn('git add -- docs/dataset-downloads.json docs/demo-preview.json',commit)
        self.assertNotIn('git add .',commit)

    def test_notebook_syntax_and_job_values_require_python_language(self):
        for path in (ROOT / "notebooks").glob("*.ipynb"):
            notebook = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(notebook["metadata"]["application/vnd.databricks.v1+notebook"]["language"], "python")
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] == "code":
                    ast.parse("".join(cell["source"]).removeprefix("%python\n"), filename=f"{path.name}:{index + 1}")
        for path in (ROOT / "notebooks").glob("*.py"):
            self.assertTrue(path.read_text().startswith("# Databricks notebook source"))
            ast.parse(path.read_text(), filename=str(path))


if __name__ == "__main__":
    unittest.main()
