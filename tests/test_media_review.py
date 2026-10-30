import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_review import review

spec = importlib.util.spec_from_file_location("review_demo", ROOT / "examples/media_review/demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class MediaReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "demo"
        self.m = demo.build_demo(self.root)

    def check(self, manifest=None, probe=None):
        return review(manifest or self.m, self.root, probe)

    def refresh(self, name):
        item = self.m["artifacts"][name]
        item["sha256"] = hashlib.sha256((self.root / item["path"]).read_bytes()).hexdigest()

    def test_valid_numbers_do_not_imply_review_or_acceptance(self):
        report = self.check()
        self.assertEqual(report["automated_status"], "passed")
        self.assertEqual(report["display_facts"]["A"]["value"], "1.5")
        self.assertTrue(all(v == "unknown" for v in report["coverage"].values()))

    def test_source_change_invalidates_transitive_dependents(self):
        (self.root / "synthetic-results.json").write_text('{"a_s":120,"b_s":30}', encoding="utf-8")
        report = self.check()
        self.assertEqual(set(report["invalidated"]), {"chart", "captions", "preview"})
        self.assertNotIn("A", report["display_facts"])

    def test_fresh_source_hash_cannot_rescue_old_build_dependencies(self):
        path = self.root / "presentation.json"
        path.write_text('{"unit":"s"}', encoding="utf-8")
        self.m["inputs"]["style"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(set(self.check()["invalidated"]), {"chart", "captions", "preview"})

    def test_display_units_and_rounding_match_across_outputs(self):
        self.m["bindings"][0]["unit"] = "s"
        self.assertEqual(self.check()["automated_status"], "failed")
        self.m["bindings"][0].update(unit="min", value="1.50")
        self.assertEqual(self.check()["automated_status"], "failed")

    def test_fact_must_have_result_dependency(self):
        self.m["artifacts"]["chart"]["depends_on"].pop("results")
        self.assertTrue(any(c["code"] == "binding" and c["status"] == "failed" for c in self.check()["checks"]))

    def test_monte_carlo_claim_requires_sampling_and_replicates(self):
        exp = self.m["experiments"]["demo"]
        exp.update(kind="expectation_estimate", replicates=1)
        self.assertEqual(self.check()["automated_status"], "failed")
        exp.update(replicates=16, sampling="paired independent synthetic runs", uncertainty="paired mean CI; fixture only")
        self.assertEqual(self.check()["automated_status"], "passed")

    def test_global_decision_requires_each_current_target(self):
        del self.m["decisions"][0]["applied"]["captions"]
        self.assertEqual(self.check()["automated_status"], "failed")

    def test_changed_artifact_cannot_keep_old_annotation_completion(self):
        (self.root / "captions.txt").write_text("Revised wording: 1.5 min, 0.5 min", encoding="utf-8")
        self.refresh("captions")
        self.assertTrue(any(c["code"] == "decision" and c["status"] == "failed" for c in self.check()["checks"]))

    def test_intentional_static_is_allowed_but_action_as_still_fails(self):
        self.assertEqual(self.check()["automated_status"], "passed")
        self.m["scenes"][0].update(motion_required=True, action="door opens")
        self.assertEqual(self.check()["automated_status"], "failed")

    def test_no_probe_or_probe_error_is_unknown(self):
        self.m["scenes"][0].update(media_kind="video", motion_required=True, action="door opens", motion={})
        self.assertEqual(self.check()["automated_status"], "incomplete")
        def broken(*args):
            raise RuntimeError("decoder absent")
        self.assertEqual(self.check(probe=broken)["automated_status"], "incomplete")
        self.assertEqual(self.check(probe=lambda *_: dict(status="failed"))["automated_status"], "failed")

    def test_review_evidence_does_not_transfer_to_changed_content(self):
        artifact = self.m["artifacts"]["captions"]
        self.m["reviews"] = [dict(artifact="captions", category="semantic", sha256=artifact["sha256"],
                                   status="passed", reviewer="fixture", reference="fixture observation", scope="whole_artifact")]
        (self.root / "captions.txt").write_text("Changed", encoding="utf-8")
        self.refresh("captions")
        report = self.check()
        self.assertEqual(report["coverage"]["semantic"], "unknown")
        self.assertTrue(any(c["code"] == "review" and c["status"] == "failed" for c in report["checks"]))

    def test_partial_playback_cannot_claim_full_coverage(self):
        a = self.m["artifacts"]["chart"]
        self.m["reviews"] = [dict(artifact="chart", category="playback", sha256=a["sha256"],
                                   status="passed", reviewer="fixture", reference="first frame only", scope="first_frame")]
        self.assertEqual(self.check()["automated_status"], "failed")

    def test_cycle_and_unknown_dependency_fail(self):
        self.m["artifacts"]["chart"]["depends_on"]["preview"] = self.m["artifacts"]["preview"]["sha256"]
        self.assertEqual(self.check()["automated_status"], "failed")
        self.m["artifacts"]["chart"]["depends_on"] = {"absent": "0"*64}
        self.assertEqual(self.check()["automated_status"], "failed")

    def test_nonfinite_fact_fails(self):
        path = self.root / "synthetic-results.json"
        path.write_text('{"a_s": "NaN", "b_s":30}', encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.m["inputs"]["results"]["sha256"] = digest
        for name in ("chart", "captions"):
            self.m["artifacts"][name]["depends_on"]["results"] = digest
        self.assertEqual(self.check()["automated_status"], "failed")

    def test_cli_uncovered_review_is_not_success_and_report_not_overwritten(self):
        self.m["required_reviews"] = ["playback"]
        manifest = self.root / "revision.json"
        manifest.write_text(json.dumps(self.m), encoding="utf-8")
        output = self.root / "review-cli.json"
        command = [sys.executable, str(ROOT / "scripts/media_review.py"), str(manifest), "--report", str(output)]
        first = subprocess.run(command, capture_output=True)
        self.assertEqual(first.returncode, 2)
        original = output.read_bytes()
        second = subprocess.run(command, capture_output=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(output.read_bytes(), original)

    def test_empty_manifest_cannot_pass(self):
        report = review(dict(schema_version=1, revision="empty", inputs={}, artifacts={}), self.root)
        self.assertEqual(report["automated_status"], "failed")

    def test_review_scope_can_target_only_the_final_preview(self):
        a = self.m["artifacts"]["preview"]
        self.m["review_targets"] = {"semantic": ["preview"]}
        self.m["required_reviews"] = ["semantic"]
        self.m["reviews"] = [dict(artifact="preview", category="semantic", sha256=a["sha256"],
                                   status="passed", reviewer="fixture", reference="synthetic review record", scope="whole_artifact")]
        report = self.check()
        self.assertEqual(report["required_uncovered"], [])
        self.assertEqual(report["coverage"]["semantic"], "passed")
        self.assertEqual(report["coverage"]["acceptance"], "unknown")

    def test_malformed_records_fail_before_media_checks(self):
        self.m["scenes"] = ["not a scene object"]
        self.assertEqual(self.check()["automated_status"], "failed")


if __name__ == "__main__":
    unittest.main()
