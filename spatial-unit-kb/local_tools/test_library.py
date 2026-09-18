import copy
from pathlib import Path
import tempfile
import unittest

from library import Library


def card():
    return {"title": "Arithmetic mean", "content": "Describe supplied measurements.",
            "conditions": "Comparable quantities with a common unit.",
            "limitations": "A descriptive mean does not identify a mechanism.",
            "basis": "direct", "rationale": "Tutorial note states the expression.",
            "expression": "mean = sum(x_i) / n",
            "symbols": {"x_i": "observed value in a common unit", "n": "number of values, positive"}}


def plan():
    return {"title": "Descriptive draft", "question": "What is the average recorded measurement?",
            "data_requirements": "Numeric measurements with known and consistent units.",
            "alternatives": "Description alone cannot distinguish causal explanations.",
            "steps": [{"action": "Compute and report the mean.", "purpose": "Describe this sample.",
                       "basis": "direct", "rationale": "Use the registered formula under its stated conditions.",
                       "refs": [{"id": "FORM-MEAN", "version": 1}]}],
            "outputs": "Table of counts, units and mean.",
            "interpretation_limits": "Draft only; no observations or causal conclusions."}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.note = self.root / "note.md"
        self.note.write_text("Synthetic note: mean = sum(x_i) / n, n > 0. Common units required.", encoding="utf-8")
        self.lib = Library(self.root)
        self.source = self.lib.register_source("SRC-NOTE", "note.md", "Synthetic tutorial", "user_note")
        self.refs = [{"id": "SRC-NOTE", "version": 1}]

    def save_formula(self):
        return self.lib.save_card("FORM-MEAN", "formula", card(), self.refs)

    def test_source_archived_and_page_optional(self):
        self.note.unlink()
        self.save_formula()
        trail = self.lib.trace("FORM-MEAN")
        self.assertEqual(len(trail["files"]), 1)
        self.assertTrue(trail["files"][0]["file_verified"])
        self.assertEqual(self.source["data"]["reading_depth"], "not_assessed")

    def test_revision_preserves_old_file_and_formula_reference(self):
        self.save_formula()
        self.note.write_text("New source version.", encoding="utf-8")
        self.lib.register_source("SRC-NOTE", "note.md", "Revised note", "user_note", expected_version=1)
        self.assertEqual(self.lib.get("SRC-NOTE")["version"], 2)
        self.assertEqual(self.lib.trace("FORM-MEAN")["files"][0]["sha256"], self.source["data"]["sha256"])
        with self.assertRaisesRegex(ValueError, "stale"):
            self.lib.register_source("SRC-NOTE", "note.md", "stale")
        self.assertEqual(self.lib.get("SRC-NOTE", 1), self.source)

    def test_plan_traces_every_step_and_does_not_record_result(self):
        self.save_formula()
        saved = self.lib.save_plan("PLAN-1", plan())
        self.assertEqual(saved["record_status"], "draft_unverified")
        self.assertEqual(len(self.lib.trace("PLAN-1")["records"]), 3)
        self.assertEqual(len(self.lib.trace("PLAN-1")["files"]), 1)
        self.assertFalse((self.root / "spatial-unit-kb/data/real_summary").exists())

    def test_unbacked_step_and_false_result_fields_rejected(self):
        self.save_formula()
        bad = plan()
        bad["steps"].append({"action": "Unsupported", "purpose": "test", "basis": "original", "rationale": "test", "refs": []})
        with self.assertRaises(ValueError):
            self.lib.save_plan("PLAN-FAIL", bad)
        self.assertEqual(self.lib.list(kind="experiment_plan")["total_matches"], 0)
        bad = plan()
        bad["observed_result"] = "pretend"
        with self.assertRaises(ValueError):
            self.lib.save_plan("PLAN-FAIL", bad)

    def test_wrong_refs_and_stale_revision(self):
        self.save_formula()
        with self.assertRaises(ValueError):
            self.lib.save_card("FORM-OTHER", "formula", card(), [{"id": "FORM-MEAN", "version": 1}])
        with self.assertRaises(ValueError):
            self.lib.save_card("FORM-OTHER", "formula", card(), [{"id": "MISSING", "version": 1}])
        with self.assertRaisesRegex(ValueError, "stale"):
            self.save_formula()
        changed = card()
        changed["limitations"] = "Revised bounded limitation."
        self.lib.save_card("FORM-MEAN", "formula", changed, self.refs, 1)
        self.assertEqual(self.lib.get("FORM-MEAN", 1)["data"], card())
        with self.assertRaises(ValueError):
            self.lib.save_card("FORM-BOOL", "formula", card(), [{"id": "SRC-NOTE", "version": True}])

    def test_corrupt_and_missing_archives_rejected(self):
        self.save_formula()
        path = Path(self.lib.trace("FORM-MEAN")["files"][0]["path"])
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.lib.trace("FORM-MEAN")
        with self.assertRaises(ValueError):
            self.lib.save_plan("PLAN-BAD", plan())
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.lib.trace("FORM-MEAN")

    def test_namespace_and_workspace_boundaries(self):
        demo = Library(self.root, "demo")
        self.assertEqual(demo.status()["counts"]["source"], 0)
        with self.assertRaises(ValueError):
            demo.save_card("FORM-X", "formula", card(), self.refs)
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stage"):
                self.lib.register_source("SRC-OUTSIDE", str(outside), "outside")
        with self.assertRaises(ValueError):
            Library(self.root, "../bad")

    def test_read_only_status_does_not_initialize(self):
        root = self.root / "fresh"
        lib = Library(root)
        self.assertFalse(lib.status()["initialized"])
        self.assertFalse(root.exists())

    def test_search_metadata_and_cards_not_fulltext(self):
        self.save_formula()
        self.assertEqual(self.lib.list("ARITHMETIC", "formula")["total_matches"], 1)
        self.assertEqual(self.lib.list("unmatched")["total_matches"], 0)
        with self.assertRaises(ValueError):
            self.lib.list(limit=0)

    def test_200_sources_and_web_snapshot(self):
        for i in range(199):
            self.lib.register_source("SRC-" + str(i), "note.md", "Article " + str(i))
        self.assertEqual(self.lib.status()["counts"]["source"], 200)
        self.assertEqual(len(list((self.lib.root / "files").iterdir())), 1)
        with self.assertRaises(ValueError):
            self.lib.register_source("SRC-WEB", "note.md", "snapshot", "web")
        source = self.lib.register_source("SRC-WEB", "note.md", "snapshot", "web", "https://example.org/tutorial")
        self.assertEqual(source["data"]["source_type"], "web")
        self.assertEqual(self.lib.status()["counts"]["source"], 201)


if __name__ == "__main__":
    unittest.main()
