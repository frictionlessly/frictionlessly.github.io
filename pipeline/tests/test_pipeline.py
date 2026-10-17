from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid

from pipeline.delivery import (
    PipelineError, customer_lock, main, read_json, validate_config, write_json,
)
from pipeline.evidence import EvidenceError, parse_evidence


FAKE_LLM = """
import json
from pathlib import Path
site = Path('site/index.html')
site.write_text(site.read_text().replace('<button>Contact</button>', '<a href="#contact">Contact</a>'))
output = Path('.pipeline-output')
output.mkdir(exist_ok=True)
(output / 'change.json').write_text(json.dumps({
    'summary': 'Changed the contact button to an in-page link.',
    'changed_files': ['index.html'],
    'reason': 'The agreed navigation now has a real destination.',
    'limitations': ['Visual review and real measurements are still required.']
}))
(output / 'usage.json').write_text(json.dumps({'test_fixture_tokens': 7}))
print('Synthetic test CLI completed, not a real provider call.')
"""


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path("pipeline/.test-runs").absolute() / uuid.uuid4().hex
        self.base.mkdir(parents=True)
        self.root = self.base / "state"
        self.source = self.base / "source"
        self.source.mkdir()
        self.original = '<html><button>Contact</button><section id="contact">Original</section></html>'
        (self.source / "index.html").write_text(self.original)
        self.config = {
            "schema_version": 1,
            "customer_id": "test-customer",
            "customer_name": "Synthetic test customer",
            "source_dir": str(self.source),
            "source_paths": ["index.html"],
            "authorization": {
                "owner_approved": True, "approved_by": "Test operator",
                "reference": "synthetic-fixture", "scope": "One local contact link",
            },
            "agreed_fix": {
                "description": "Replace the inert Contact button with a #contact link.",
                "acceptance": "A real #contact link and its section exist.",
                "allowed_paths": ["index.html"],
            },
            "llm": {
                "argv": [sys.executable, "-c", FAKE_LLM],
                "prompt_mode": "argument", "timeout_seconds": 5, "max_calls_per_month": 2,
            },
            "verification": [{
                "name": "contact-behavior", "purpose": "Assert the contact link and destination",
                "argv": [
                    sys.executable, "-c",
                    "from pathlib import Path; s=Path('index.html').read_text(); "
                    "assert '<a href=\"#contact\">Contact</a>' in s; "
                    "assert 'id=\"contact\"' in s",
                ],
                "timeout_seconds": 5,
            }],
        }
        self.config_path = self.base / "customer.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.base)

    def cli(self, *args: str, expected: int = 0) -> dict:
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["--root", str(self.root), *args])
        self.assertEqual(code, expected, errors.getvalue() + output.getvalue())
        return json.loads(output.getvalue()) if output.getvalue().strip() else {}

    def action(self, action: str, *args: str, expected: int = 0, month: str = "2026-10") -> dict:
        return self.cli(
            action, "--customer", "test-customer", "--month", month, *args, expected=expected
        )

    def prepare(self) -> Path:
        write_json(self.config_path, self.config)
        self.cli("onboard", "--config", str(self.config_path))
        return Path(self.action("prepare")["run"])

    def test_prepare_is_offline_and_excludes_private_source(self) -> None:
        assets = self.source / "assets"
        assets.mkdir()
        (assets / "logo.svg").write_text("<svg/>")
        (assets / ".env").write_text("SYNTHETIC_SECRET=not-real")
        (assets / "credentials.json").write_text("{}")
        modules = assets / "node_modules"
        modules.mkdir()
        (modules / "ignored-symlink").symlink_to(self.base)
        self.config["source_paths"].append("assets")
        instructions = self.base / "operator.txt"
        instructions.write_text("Trusted synthetic operator recipe.")
        self.config["instructions_file"] = str(instructions)
        run = self.prepare()
        state = read_json(run / "state.json")
        self.assertEqual(state["status"], "prepared")
        self.assertEqual(state["llm_calls"], 0)
        self.assertEqual((run / "baseline/index.html").read_text(), self.original)
        self.assertEqual((self.source / "index.html").read_text(), self.original)
        self.assertTrue((run / "work/site/assets/logo.svg").exists())
        self.assertFalse((run / "baseline/assets/.env").exists())
        self.assertFalse((run / "work/site/assets/credentials.json").exists())
        self.assertFalse((run / "work/site/assets/node_modules").exists())
        self.assertFalse((run / "baseline/index.html").stat().st_mode & 0o222)
        self.assertIn("Trusted synthetic operator recipe.", (run / "prompt.txt").read_text())
        self.assertIn("ORDERED ACTIONS", (run / "prompt.txt").read_text())
        second = Path(self.action("prepare")["run"])
        self.assertNotEqual(run, second)
        self.assertTrue((run / "state.json").exists())

    def test_run_checks_report_approval_and_tamper_detection(self) -> None:
        run = self.prepare()
        state = self.action("run")
        self.assertEqual(state["status"], "ready_for_review")
        self.assertEqual(state["checks"][0]["status"], "passed")
        self.assertEqual((self.source / "index.html").read_text(), self.original)
        report = (run / "report.md").read_text()
        self.assertIn("not measured/unavailable", report)
        self.assertIn("Conversion uplift is not established", report)
        self.assertIn("not independent evidence", report)
        self.assertIn("+<html>", (run / "changes.diff").read_text())
        self.assertEqual(read_json(run / "usage.json")["reported_usage"], {"test_fixture_tokens": 7})
        reviewed_hash = state["artifact_sha256"]
        approved = self.action(
            "approve", "--reviewer", "Human test operator", "--artifact-sha256", reviewed_hash
        )
        self.assertEqual(approved["status"], "approval_recorded")
        record = read_json(run / approved["approval"])
        self.assertEqual(record["artifact_sha256"], reviewed_hash)
        self.assertEqual(record["publishing"], "not_performed")
        self.assertEqual(self.action("status")["status"], "approval_recorded")
        with (run / "work/site/index.html").open("a") as handle:
            handle.write("\n<!-- reviewed local adjustment -->")
        self.assertEqual(self.action("status", expected=2)["status"], "stale_requires_verification")
        verified = self.action("verify")
        self.assertNotEqual(verified["artifact_sha256"], reviewed_hash)
        self.assertIsNone(verified["approval"])
        self.assertEqual(read_json(run / "state.json")["llm_calls"], 1)

    def test_empty_checks_block_without_faking_success(self) -> None:
        self.config["verification"] = []
        run = self.prepare()
        state = self.action("run", expected=2)
        self.assertEqual(state["status"], "blocked_unverified")
        self.assertFalse((run / "artifact-manifest.json").exists())
        self.assertIn("No operator-authored verification", (run / "report.md").read_text())
        self.action("approve", "--reviewer", "Human", "--artifact-sha256", "wrong", expected=1)

    def test_failing_check_persists_and_verify_can_recover_without_llm(self) -> None:
        self.config["verification"][0]["argv"] = [
            sys.executable, "-c",
            "from pathlib import Path; assert '<!-- approved test marker -->' in Path('index.html').read_text()",
        ]
        run = self.prepare()
        self.action("run", expected=1)
        state = read_json(run / "state.json")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["checks"][0]["status"], "failed")
        self.assertTrue((run / "checks/001/results.json").exists())
        with (run / "work/site/index.html").open("a") as handle:
            handle.write("<!-- approved test marker -->")
        recovered = self.action("verify")
        self.assertEqual(recovered["status"], "ready_for_review")
        self.assertEqual(recovered["llm_calls"], 1)
        self.assertTrue((run / "checks/002/results.json").exists())

    def test_llm_timeout_and_monthly_budget_include_failed_calls(self) -> None:
        self.config["llm"].update(
            argv=[sys.executable, "-c", "import time; time.sleep(10)"],
            timeout_seconds=1, max_calls_per_month=1,
        )
        run = self.prepare()
        self.action("run", expected=1)
        self.assertEqual(read_json(run / "llm-result.json")["status"], "timed_out")
        self.assertEqual(read_json(run / "state.json")["llm_calls"], 1)
        retry = Path(self.action("prepare")["run"])
        self.action("run", expected=1)
        self.assertIn("budget exhausted", read_json(retry / "state.json")["error"])
        self.assertFalse((retry / "llm.log").exists())
        self.assertEqual(read_json(retry / "state.json")["llm_calls"], 0)
        next_month = Path(self.action("prepare", month="2026-11")["run"])
        self.assertEqual(next_month.name, "001")

    def test_model_prose_or_out_of_scope_changes_do_not_pass(self) -> None:
        for script, message in (
            ("print('Everything passed!')", "No agreed source fix"),
            (FAKE_LLM + "\nPath('site/unapproved.txt').write_text('extra')", "file scope"),
            (FAKE_LLM + "\nPath('.pipeline-output/change.json').write_text('{}')", "schema"),
            ("raise SystemExit(3)", "LLM command failed"),
        ):
            with self.subTest(message=message):
                self.config["llm"]["argv"] = [sys.executable, "-c", script]
                self.config["llm"]["max_calls_per_month"] = 10
                run = self.prepare()
                self.action("run", expected=1)
                self.assertIn(message, read_json(run / "state.json")["error"])
                self.assertFalse((run / "artifact-manifest.json").exists())

    def test_missing_executable_failure_is_persistent(self) -> None:
        self.config["llm"]["argv"] = [str(self.base / "not-an-installed-cli")]
        run = self.prepare()
        self.action("run", expected=1)
        self.assertEqual(read_json(run / "llm-result.json")["status"], "failed")
        self.assertEqual(read_json(run / "state.json")["status"], "failed")

    def test_modified_baseline_and_symlink_escape_fail(self) -> None:
        run = self.prepare()
        baseline = run / "baseline/index.html"
        baseline.chmod(0o600)
        baseline.write_text("tampered")
        self.action("run", expected=1)
        self.assertIn("baseline", read_json(run / "state.json")["error"])
        self.assertFalse((run / "llm.log").exists())
        (self.source / "escape.html").symlink_to(self.config_path)
        self.config["source_paths"].append("escape.html")
        write_json(self.config_path, self.config)
        self.cli("onboard", "--config", str(self.config_path), expected=1)

    def test_verifier_source_mutation_requires_another_stable_check(self) -> None:
        self.config["verification"][0]["argv"] = [
            sys.executable, "-c",
            "from pathlib import Path; p=Path('index.html'); p.write_text(p.read_text()+'\\n')",
        ]
        run = self.prepare()
        self.action("run", expected=1)
        self.assertIn("Verification changed", read_json(run / "state.json")["error"])
        self.assertFalse((run / "artifact-manifest.json").exists())

    def test_evidence_import_invalidates_approval_and_preserves_unknown_vs_zero(self) -> None:
        run = self.prepare()
        state = self.action("run")
        self.action("approve", "--reviewer", "Human", "--artifact-sha256", state["artifact_sha256"])
        metrics = self.base / "metrics.json"
        write_json(metrics, {
            "period": "2026-10", "source": "Synthetic zero-count test fixture",
            "sessions": 0, "enquiries": None, "conversion_rate_percent": None,
        })
        imported = self.action(
            "import-evidence", "--kind", "metrics", "--phase", "monthly", "--file", str(metrics)
        )
        self.assertEqual(imported["status"], "needs_verification")
        self.assertIsNone(imported["approval"])
        checked = self.action("verify")
        self.assertEqual(checked["status"], "ready_for_review")
        self.assertIn("Sessions: 0.", (run / "report.md").read_text())
        self.assertIn("Enquiries: not measured/unavailable", (run / "report.md").read_text())
        self.assertNotEqual(checked["artifact_sha256"], state["artifact_sha256"])
        self.assertEqual(len(read_json(run / "evidence-index.json")), 1)

    def test_invalid_config_records_failure_and_customer_lock_prevents_races(self) -> None:
        self.config["authorization"]["owner_approved"] = False
        write_json(self.config_path, self.config)
        self.cli("onboard", "--config", str(self.config_path), expected=1)
        self.assertEqual(len(list((self.root / "failures").glob("*.json"))), 1)
        self.config["authorization"]["owner_approved"] = True
        self.prepare()
        with customer_lock(self.root, "test-customer"):
            self.action("prepare", expected=1)
        self.assertEqual(self.action("status")["status"], "prepared")

    def test_validates_scope_budget_and_permission_flags(self) -> None:
        cases = [
            ("customer_id", "../escape"),
            ("source_paths", ["../outside"]),
            ("source_paths", [".env"]),
            ("verification", "not-an-array"),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                config = json.loads(json.dumps(self.config))
                config[key] = value
                with self.assertRaises(PipelineError):
                    validate_config(config, self.base, self.root)
        for flag in ("--allow-all", "--yolo", "--allow-all-tools"):
            config = json.loads(json.dumps(self.config))
            config["llm"]["argv"].append(flag)
            with self.assertRaises(PipelineError):
                validate_config(config, self.base, self.root)
        self.config["llm"]["max_calls_per_month"] = 0
        with self.assertRaises(PipelineError):
            validate_config(self.config, self.base, self.root)

    def test_stdin_mode_delivers_prompt_without_shell_expansion(self) -> None:
        self.config["llm"]["prompt_mode"] = "stdin"
        self.config["llm"]["argv"] = [
            sys.executable, "-c",
            "import sys; prompt=sys.stdin.read(); assert 'ORDERED ACTIONS' in prompt\n" + FAKE_LLM,
        ]
        run = self.prepare()
        self.action("run")
        self.assertEqual(read_json(run / "llm-result.json")["returncode"], 0)

    def test_interrupted_state_is_not_mistaken_for_running_success(self) -> None:
        run = self.prepare()
        state = read_json(run / "state.json")
        state["status"] = "running"
        state["llm_calls"] = 1
        write_json(run / "state.json", state)
        result = self.action("status", expected=2)
        self.assertEqual(result["status"], "failed")
        self.assertIn("interrupted", result["error"])

    def test_checked_in_demo_works_with_its_real_acceptance_command(self) -> None:
        example = read_json(Path("pipeline/examples/customer.json"))
        self.config["verification"] = example["verification"]
        shutil.copyfile(Path("pipeline/examples/site/index.html"), self.source / "index.html")
        fake = FAKE_LLM.replace(
            "'<button>Contact</button>', '<a href=\"#contact\">Contact</a>'",
            "'<button class=\"button\">Get a quote</button>', "
            "'<a class=\"button\" href=\"#contact\">Get a quote</a>'",
        )
        self.config["llm"]["argv"] = [sys.executable, "-c", fake]
        run = self.prepare()
        result = self.action("run")
        self.assertEqual(result["status"], "ready_for_review")
        self.assertIn("assertions passed", (run / "checks/001/01.log").read_text())

    def test_wrong_approval_hash_and_invalid_evidence_never_stay_approved(self) -> None:
        run = self.prepare()
        self.action("run")
        self.action("approve", "--reviewer", "Human", "--artifact-sha256", "not-the-hash", expected=1)
        self.assertEqual(read_json(run / "state.json")["status"], "failed")
        self.assertFalse((run / "approvals").exists())
        self.action("verify")
        bad = self.base / "bad.json"
        bad.write_text('{"sessions": NaN}')
        self.action(
            "import-evidence", "--kind", "metrics", "--phase", "monthly",
            "--file", str(bad), expected=1,
        )
        self.assertFalse((run / "evidence-index.json").exists())
        self.assertEqual(read_json(run / "state.json")["status"], "failed")

    def test_evidence_summary_cannot_diverge_from_imported_raw_data(self) -> None:
        run = self.prepare()
        metrics = self.base / "metrics.json"
        write_json(metrics, {"period": "2026-10", "source": "Synthetic fixture", "sessions": None})
        self.action("import-evidence", "--kind", "metrics", "--phase", "monthly", "--file", str(metrics))
        self.action("run")
        index = read_json(run / "evidence-index.json")
        index[0]["parsed"]["sessions"] = 999
        write_json(run / "evidence-index.json", index)
        self.action("verify", expected=1)
        self.assertEqual(read_json(run / "state.json")["status"], "failed")
        self.assertIn("raw input", read_json(run / "state.json")["error"])

    def test_report_only_month_needs_no_fake_edit_or_llm_call(self) -> None:
        run = self.prepare()
        result = self.action("report")
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(result["llm_calls"], 0)
        self.assertFalse((run / "llm.log").exists())
        self.assertEqual((run / "changes.diff").read_text(), "")
        self.assertIn("no source changes were made", (run / "report.md").read_text())
        approved = self.action(
            "approve", "--reviewer", "Human", "--artifact-sha256", result["artifact_sha256"]
        )
        self.assertEqual(
            read_json(run / approved["approval"])["decision"], "approved_for_manual_report_handoff"
        )
        (run / "work/site/index.html").write_text("unreviewed change")
        self.action("report", expected=1)
        self.assertIn("unchanged working snapshot", read_json(run / "state.json")["error"])

    def test_report_retains_each_device_and_audit_source(self) -> None:
        run = self.prepare()
        for device, wrapped, score in (("mobile", True, 0.61), ("desktop", False, 0.95)):
            raw = {
                "finalUrl": "https://example.com/",
                "fetchTime": "2026-10-17T12:00:00Z",
                "lighthouseVersion": "test-version",
                "configSettings": {"formFactor": device},
                "categories": {"performance": {"score": score}},
            }
            evidence = self.base / f"{device}.json"
            write_json(evidence, {"lighthouseResult": raw} if wrapped else raw)
            self.action(
                "import-evidence", "--kind", "lighthouse", "--phase", "baseline",
                "--file", str(evidence),
            )
        self.action("report")
        report = (run / "report.md").read_text()
        for expected in ("Baseline - mobile", "Baseline - desktop", "PageSpeed Insights",
                         "Lighthouse export", "61.0", "95.0", "test-version"):
            self.assertIn(expected, report)


class EvidenceTests(unittest.TestCase):
    def test_lighthouse_and_psi_preserve_absent_metrics(self) -> None:
        fixture = {
            "finalUrl": "http://localhost:8000/",
            "fetchTime": "2026-10-17T12:00:00Z",
            "categories": {"performance": {"score": 0}},
            "configSettings": {"formFactor": "mobile", "throttlingMethod": "simulate"},
            "audits": {"cumulative-layout-shift": {"numericValue": 0}},
        }
        direct = parse_evidence("lighthouse", fixture, "2026-10")
        wrapped = parse_evidence("lighthouse", {"lighthouseResult": fixture}, "2026-10")
        self.assertEqual(
            {k: v for k, v in direct.items() if k != "measurement_source"},
            {k: v for k, v in wrapped.items() if k != "measurement_source"},
        )
        self.assertEqual(wrapped["measurement_source"], "PageSpeed Insights")
        self.assertEqual(direct["performance_score"], 0)
        self.assertEqual(direct["cls"], 0)
        self.assertIsNone(direct["lcp_ms"])
        fixture["runtimeError"] = {"code": "NO_FCP"}
        with self.assertRaises(EvidenceError):
            parse_evidence("lighthouse", fixture, "2026-10")

    def test_invalid_analytics_are_rejected_not_coerced(self) -> None:
        for field, value in (
            ("sessions", True), ("sessions", -1), ("enquiries", 1.2),
            ("conversion_rate_percent", 101), ("period", "2026-09"),
            ("sessions", float("nan")),
        ):
            with self.subTest(field=field, value=value):
                fixture = {"period": "2026-10", "source": "Synthetic fixture", field: value}
                with self.assertRaises(EvidenceError):
                    parse_evidence("metrics", fixture, "2026-10")

    def test_conversion_rates_require_valid_same_cohort_counts(self) -> None:
        fixture = {
            "period": "2026-10", "source": "Synthetic verified aggregate fixture",
            "sessions": 100, "converted_sessions": 8, "enquiries": 12,
            "conversion_event": "Confirmed valid inquiry",
            "cohort": "Eligible consenting sessions, tests and bots excluded",
            "timezone": "America/Los_Angeles",
        }
        result = parse_evidence("metrics", fixture, "2026-10")
        self.assertEqual(result["conversion_rate_percent"], 8)
        self.assertEqual(result["enquiries"], 12)
        for override in (
            {"converted_sessions": 101}, {"sessions": None}, {"cohort": None},
            {"conversion_event": None}, {"converted_sessions": 1.5},
            {"conversion_rate_percent": 12}, {"timezone": "not-a-timezone"},
            {"sessions": 0, "converted_sessions": 0, "conversion_rate_percent": 0},
        ):
            with self.subTest(override=override), self.assertRaises(EvidenceError):
                parse_evidence("metrics", {**fixture, **override}, "2026-10")
        zero = parse_evidence(
            "metrics", {**fixture, "sessions": 0, "converted_sessions": 0}, "2026-10"
        )
        self.assertIsNone(zero["conversion_rate_percent"])
        missing = parse_evidence("metrics", {**fixture, "converted_sessions": None}, "2026-10")
        self.assertIsNone(missing["conversion_rate_percent"])


if __name__ == "__main__":
    unittest.main()
