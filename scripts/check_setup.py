"""Read-only local readiness checks. Does not authenticate or run the pipeline."""

import ast
from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("numpy", "pandas", "openpyxl", "pyarrow", "jsonschema")
REQUIRED = (
    "README.md", "requirements-dev.txt", "docs/setup.md", "notebooks/00_Create_Fabricated_SOURCE.py",
    "src/synthetic_banking/config.py", "src/synthetic_banking/demo_export_policy.json",
    "scripts/Scotia Fake Records.py", "databricks.yml",
    "resources/synthetic_pipeline.job.yml", "resources/demo_dataset_export.job.yml",
    "docs/index.html", "docs/records-config.js", "docs/validation-config.js",
    "docs/reporting/pipeline-report.schema.json",
)


@dataclass(frozen=True)
class Check:
    passed: bool
    message: str


def check_layout(root):
    """Catch incomplete notebook-only uploads and broken bundle notebook paths."""
    root = Path(root).resolve()
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        return Check(False, "Incomplete project; restore: " + ", ".join(missing))
    for resource in (root / "resources").glob("*.yml"):
        # Only inspect the repository's simple notebook_path scalars, not general YAML.
        for relative in re.findall(r"^\s+notebook_path: (.+)$", resource.read_text(encoding="utf-8"), re.M):
            target = (resource.parent / relative.strip()).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                return Check(False, "Bundle notebook missing or outside project: " + resource.name)
    return Check(True, "Project layout and bundle notebook paths")


def check_notebooks(root):
    """Check Python cells and local module imports without requiring Spark."""
    root = Path(root)
    notebooks = sorted((root / "notebooks").glob("*.ipynb"))
    if not notebooks:
        return Check(False, "Missing main notebooks")
    try:
        for path in notebooks:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] != "code":
                    continue
                tree = ast.parse("".join(cell["source"]).removeprefix("%python\n"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("synthetic_banking."):
                        module_path = root / "src" / Path(*node.module.split("."))
                        if not module_path.with_suffix(".py").is_file():
                            return Check(False, "Notebook module missing: " + node.module)
        for path in (root / "notebooks").glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"))
    except (ValueError, KeyError, TypeError, SyntaxError):
        return Check(False, "Invalid notebook JSON/Python; restore notebooks before running")
    return Check(True, "Notebook Python syntax and shared-module references")


def check_demo_generator(root):
    """A code fingerprint is necessary for replay; it does not verify dataset origin."""
    root = Path(root)
    try:
        policy = json.loads((root / "src/synthetic_banking/demo_export_policy.json").read_text(encoding="utf-8"))
        content = (root / "scripts/Scotia Fake Records.py").read_text(encoding="utf-8").replace("\r\n", "\n")
        matches = hashlib.sha256(content.encode("utf-8")).hexdigest() == policy["generator_sha256"]
    except (OSError, ValueError, KeyError):
        matches = False
    return Check(matches, "Pinned fabricated-generator fingerprint" if matches else
                 "Fabricated generator differs from reviewed policy; restore it, do not bypass replay")


def check_packages():
    checks = []
    for name in PACKAGES:
        try:
            importlib.import_module(name)
        except Exception:
            checks.append(Check(False, name + " unavailable; install requirements-dev.txt in your virtual environment"))
        else:
            checks.append(Check(True, name + " imports"))
    return checks


def check_node():
    executable = shutil.which("node")
    if executable:
        try:
            result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=True)
            match = re.fullmatch(r"v(\d+)\.\d+\.\d+\s*", result.stdout)
            if match and int(match[1]) >= 18:
                return Check(True, "Node.js supports the frontend test runner (CI uses Node 22)")
        except (OSError, subprocess.SubprocessError):
            pass
    return Check(False, "Node.js 18+ required for frontend checks; use Node 22 to match CI")


def main():
    if sys.version_info < (3, 10):
        print("FAIL Python 3.10+ required; use Python 3.12 to match CI")
        return 1
    checks = [Check(sys.version_info >= (3, 10), "Python 3.10+ required (CI uses 3.12)"),
              Check(sqlite3.sqlite_version_info >= (3, 39), "SQLite 3.39+ required for all local SQL-adapter tests"),
              check_layout(ROOT), check_notebooks(ROOT), check_demo_generator(ROOT), *check_packages(), check_node()]
    if all(check.passed for check in checks):
        sys.path.insert(0, str(ROOT / "src"))
        try:
            for path in sorted((ROOT / "src/synthetic_banking").glob("*.py")):
                importlib.import_module("synthetic_banking." + path.stem)
        except Exception:
            checks.append(Check(False, "Shared module import failed; run the Python suite for details"))
        else:
            checks.append(Check(True, "All shared modules import without Spark or credentials"))
    for check in checks:
        print(("PASS " if check.passed else "FAIL ") + check.message)
    print("Local checks only. Databricks permissions, Volumes, model access and Delta execution still need an authenticated smoke test.")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
