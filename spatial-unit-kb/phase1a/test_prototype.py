import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prototype import build_demo, link, resume
from store import Store, IntegrityError, ConflictError, proposal

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "demo"
        self.store = Store(self.path, "demo")
        self.initial = build_demo(WORKSPACE, "A1")

    def tearDown(self):
        self.temp.cleanup()

    def item(self, ident, expected_version=0):
        return next(r for r in self.initial if r["id"] == ident and r["expected_version"] == expected_version)

    def test_branch_outcomes_and_old_versions(self):
        for branch, expected in (("A1", "weakened"), ("A2", "supported_within_tested_scenarios"), ("A3", "unresolved")):
            with self.subTest(branch=branch):
                store = Store(Path(self.temp.name) / branch, "demo")
                store.commit(build_demo(WORKSPACE, branch))
                restored = Store(store.directory, "demo")
                self.assertEqual(restored.get("H-001", 1)["data"]["status"], "unresolved")
                self.assertEqual(restored.get("H-001", 2)["data"]["status"], "unresolved")
                self.assertEqual(restored.get("MC-EVAL-001", 1)["data"]["status"], "unresolved")
                self.assertEqual(restored.get("MC-EVAL-001", 2)["data"]["status"], expected)
                self.assertEqual(restored.get("BC-001")["refs"]["target"], [link("MC-EVAL-001")])
                self.assertEqual(restored.get("BC-H-001")["refs"]["target"], [link("H-001")])
                self.assertEqual(restored.get("RS-001", 1)["refs"].keys(), {"evidence"})
                self.assertEqual(restored.get("RS-001")["version"], 2)

    def test_invalid_late_reference_rolls_back_entire_transaction(self):
        self.initial[-1]["refs"]["memory"] = [link("MISSING")]
        with self.assertRaises(IntegrityError):
            self.store.commit(self.initial)
        self.assertFalse(self.store.path.exists())

    def test_no_overwrite_on_stale_version(self):
        self.store.commit(self.initial)
        before = self.store.path.read_bytes()
        with self.assertRaises(ConflictError):
            self.store.commit([self.initial[0]])
        self.assertEqual(before, self.store.path.read_bytes())

    def test_demo_cannot_enter_real_namespace(self):
        with self.assertRaises(IntegrityError):
            Store(Path(self.temp.name) / "real", "real").commit(self.initial)
        self.store.commit(self.initial)
        with self.assertRaises(IntegrityError):
            Store(self.path, "real").records()

    def test_real_transition_disabled_even_if_relabelled(self):
        fake_real = copy.deepcopy(self.initial)
        for item in fake_real:
            item["category"] = "analysis"
        with self.assertRaises(IntegrityError):
            Store(Path(self.temp.name) / "real", "real").commit(fake_real)

    def test_wrong_kind_reference_rejected(self):
        self.item("INT-001")["refs"]["observations"] = [link("EV-1")]
        with self.assertRaises(IntegrityError):
            self.store.commit(self.initial)

    def test_belief_before_must_match_target(self):
        self.item("BC-001")["data"]["before"] = "proven"
        with self.assertRaises(IntegrityError):
            self.store.commit(self.initial)

    def test_revision_must_match_belief_change(self):
        self.item("MC-EVAL-001", 1)["data"]["status"] = "proven"
        with self.assertRaises(IntegrityError):
            self.store.commit(self.initial)

    def test_missing_source_rejected(self):
        self.item("OBS-001")["refs"]["evidence"] = []
        with self.assertRaises(IntegrityError):
            self.store.commit(self.initial)

    def test_corruption_detected(self):
        self.store.commit(self.initial)
        state = json.loads(self.store.path.read_text(encoding="utf-8"))
        state["records"][0]["data"]["content"] = "changed"
        self.store.path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(IntegrityError):
            self.store.records()

    def test_interrupted_replace_keeps_old_store_and_cleans_lock(self):
        self.store.commit(self.initial)
        before = self.store.path.read_bytes()
        with patch("store.os.replace", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                resume(self.store)
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertFalse((self.path / ".writer.lock").exists())
        self.assertEqual(len(list(self.path.iterdir())), 1)

    def test_existing_writer_lock_rejected(self):
        self.path.mkdir(parents=True)
        (self.path / ".writer.lock").write_text("active", encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.store.commit(self.initial)
        self.assertTrue((self.path / ".writer.lock").exists())

    def test_actual_second_process_restores_and_links_old_decision(self):
        self.store.commit(self.initial)
        old = self.store.get("DEC-001")
        result = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "prototype.py"), "resume", "--store", str(self.path)], capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        reloaded = Store(self.path, "demo")
        self.assertEqual(reloaded.get("DEC-001"), old)
        self.assertEqual(reloaded.get("DEC-002")["refs"]["previous_decisions"], [link("DEC-001")])
        self.assertEqual(reloaded.get("DEC-002")["refs"]["state"], [link("RS-001", 2)])
        self.assertEqual(reloaded.get("EV-1")["data"]["sha256"], self.initial[0]["data"]["sha256"])
        self.assertEqual(reloaded.get("DEC-002")["refs"]["changes"], [link("BC-001"), link("BC-H-001")])

    def test_method_update_cannot_silently_retarget_science(self):
        self.item("BC-001")["refs"]["target"] = [link("H-001")]
        with self.assertRaisesRegex(IntegrityError, "target_kind"):
            self.store.commit(self.initial)

    def test_claim_cannot_silently_change_meaning(self):
        self.item("MC-EVAL-001", 1)["data"]["statement"] = "真实过程已经被识别"
        with self.assertRaisesRegex(IntegrityError, "meaning is immutable"):
            self.store.commit(self.initial)

    def test_reopening_conditions_follow_branch_and_decision(self):
        seen = set()
        for branch in ("A1", "A2", "A3"):
            items = build_demo(WORKSPACE, branch)
            by_id = {r["id"]: r for r in items}
            conditions = by_id["BC-001"]["data"]["would_change_if"]
            self.assertEqual(conditions, by_id["DEC-001"]["data"]["stop_or_reopen_conditions"])
            seen.add(tuple(conditions))
        self.assertEqual(len(seen), 3)

    def test_legacy_runs_remain_readable_but_cannot_be_extended(self):
        self.store.commit(self.initial)
        state = json.loads(self.store.path.read_text(encoding="utf-8"))
        state["format"] = 1
        self.store.path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.store.get("H-001")["data"]["status"], "unresolved")
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(IntegrityError, "legacy"):
            resume(self.store)
        self.assertEqual(before, self.store.path.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
