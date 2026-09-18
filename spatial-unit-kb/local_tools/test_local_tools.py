import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_kb import Store, IntegrityError, search, provenance, validate_batch

HERE = Path(__file__).resolve().parent
from prototype import build_demo, resume


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "kb"
        self.seed = self.root / "seed"
        seed = Store(self.seed, "demo")
        seed.commit(build_demo(self.root, "A1"))
        resume(seed)
        self.call("init-demo", "--seed", str(self.seed))

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args, expected=0):
        p = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "research_kb.py"), "--store", str(self.path), *args], capture_output=True, encoding="utf-8")
        self.assertEqual(p.returncode, expected, p.stderr + p.stdout)
        return json.loads(p.stdout)

    def batch(self):
        return [{"id": "Q-CLI-001", "kind": "OpenQuestion", "expected_version": 0,
                 "category": "evaluation_injection", "scope": "CLI tool sandbox", "refs": {},
                 "data": {"unresolved_target": "真实传播机制", "why_unresolved": "模拟判别能力不能认证真实机制",
                          "needed_evidence": "有识别条件的独立真实观测"}}]

    def test_fresh_process_read_history_and_provenance(self):
        self.assertEqual(self.call("state")["version"], 2)
        self.assertEqual(self.call("get", "H-001", "--version", "1")["data"]["status"], "unresolved")
        trail = self.call("provenance", "DEC-002")
        ids = {r["id"] for r in trail["records"]}
        self.assertTrue({"DEC-001", "BC-001", "BC-H-001", "EV-INJECT", "EV-1"} <= ids)

    def test_unicode_search_and_kind_filter(self):
        result = self.call("search", "指标", "--kind", "MethodClaim")
        self.assertEqual(result["total_matches"], 1)
        self.assertEqual(result["records"][0]["version"], 2)
        self.assertEqual(self.call("search", "指标", "--kind", "MethodClaim", "--history")["total_matches"], 2)
        self.assertEqual(self.call("search", "不存在的关键词")["total_matches"], 0)

    def test_preview_write_and_stale_rejection(self):
        file = self.root / "proposal.json"
        file.write_text(json.dumps(self.batch()), encoding="utf-8")
        before = (self.path / "records.json").read_bytes()
        self.assertFalse(self.call("submit", "--file", str(file))["written"])
        self.assertEqual(before, (self.path / "records.json").read_bytes())
        self.assertTrue(self.call("submit", "--file", str(file), "--commit")["written"])
        self.assertEqual(self.call("get", "Q-CLI-001")["version"], 1)
        self.call("submit", "--file", str(file), "--commit", expected=2)

    def test_validation_rejects_wrong_namespace_and_extra_fields(self):
        batch = self.batch()
        batch[0]["category"] = "project_summary"
        with self.assertRaises(IntegrityError):
            validate_batch(Store(self.path, "demo"), batch)
        batch = self.batch()
        batch[0]["extra"] = "no"
        with self.assertRaises(IntegrityError):
            validate_batch(Store(self.path, "demo"), batch)

    def test_missing_store_does_not_succeed_or_create_files(self):
        self.path = self.root / "missing"
        self.call("validate", expected=2)
        self.assertFalse(self.path.exists())

    def test_no_silent_seed_overwrite(self):
        before = (self.path / "records.json").read_bytes()
        self.call("init-demo", "--seed", str(self.seed), expected=2)
        self.assertEqual(before, (self.path / "records.json").read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
