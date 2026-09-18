import json
import tempfile
import unittest
from pathlib import Path

from import_summaries import SOURCES, import_summaries, check_sources
from research_kb import Store, IntegrityError


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "kb", "real")
        for _, relative in SOURCES:
            path = self.root / relative
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"status": "reported", "next_decision": "unresolved", "private_extra": "MUST_NOT_IMPORT"}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_does_not_write(self):
        result = import_summaries(self.root, self.store)
        self.assertTrue(result["changed"])
        self.assertFalse(self.store.directory.exists())

    def test_import_preserves_scope_and_excludes_unlisted_fields(self):
        import_summaries(self.root, self.store, True)
        records = self.store.records()
        self.assertEqual(len(records), 4)
        self.assertFalse({"Observation", "Decision", "BeliefChange"} & {r["kind"] for r in records})
        for path in self.store.directory.rglob("*.json"):
            self.assertNotIn("MUST_NOT_IMPORT", path.read_text(encoding="utf-8"))
        self.assertEqual(check_sources(self.root, self.store)["evidence"][0]["snapshot_status"], "valid")

    def test_repeat_is_noop_and_changed_source_appends_versions(self):
        import_summaries(self.root, self.store, True)
        old = self.store.get("RS-SUMMARY-001")
        before = self.store.path.read_bytes()
        self.assertFalse(import_summaries(self.root, self.store, True)["changed"])
        self.assertEqual(before, self.store.path.read_bytes())
        source = self.root / SOURCES[0][1]
        source.write_text(json.dumps({"status": "changed"}), encoding="utf-8")
        self.assertEqual(check_sources(self.root, self.store)["evidence"][0]["source_status"], "changed")
        import_summaries(self.root, self.store, True)
        self.assertEqual(self.store.get("RS-SUMMARY-001", 1), old)
        self.assertEqual(self.store.get("EV-BACKGROUND")["version"], 2)
        self.assertEqual(self.store.get("EV-SHUFFLE")["version"], 1)
        self.assertEqual(self.store.get("RS-SUMMARY-001")["version"], 2)

    def test_missing_source_does_not_partially_import(self):
        (self.root / SOURCES[1][1]).unlink()
        with self.assertRaises(OSError):
            import_summaries(self.root, self.store, True)
        self.assertFalse(self.store.path.exists())

    def test_snapshot_tamper_and_deleted_source_are_visible(self):
        import_summaries(self.root, self.store, True)
        e = self.store.get("EV-BACKGROUND")
        (self.store.directory / e["data"]["snapshot"]).write_text("{}", encoding="utf-8")
        (self.root / SOURCES[0][1]).unlink()
        status = check_sources(self.root, self.store)["evidence"][0]
        self.assertEqual(status["snapshot_status"], "corrupt")
        self.assertEqual(status["source_status"], "missing")

    def test_demo_import_rejected(self):
        with self.assertRaises(IntegrityError):
            import_summaries(self.root, Store(self.root / "demo", "demo"), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
