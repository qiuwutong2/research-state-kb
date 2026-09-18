"""Real MCP subprocess integration, isolated demo mutations, no scientific grading."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "local_tools"))
from import_summaries import SOURCES, import_summaries
from research_kb import Store
from prototype import build_demo, resume


def payload(result):
    if result.isError:
        raise AssertionError(str(result))
    return result.structuredContent or json.loads(result.content[0].text)


class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for _, relative in SOURCES:
            source = self.root / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(json.dumps({"status": "synthetic test only"}), encoding="utf-8")
        import_summaries(self.root, Store(self.root / "spatial-unit-kb/data/real_summary", "real"), True)

    async def test_real_stdio_reads_and_namespace_boundaries(self):
        params = StdioServerParameters(command=sys.executable, args=["-X", "utf8", str(HERE / "server.py"), "--workspace", str(self.root)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = await client.list_tools()
                self.assertEqual(len(tools.tools), 13)
                self.assertTrue(next(t for t in tools.tools if t.name == "get_current_state").annotations.readOnlyHint)
                state = payload(await client.call_tool("get_current_state", {}))
                self.assertEqual(state["namespace"], "real")
                self.assertEqual(state["result"]["id"], "RS-SUMMARY-001")
                self.assertEqual(payload(await client.call_tool("get_decisions", {}))["result"], [])
                evidence = payload(await client.call_tool("get_evidence", {"evidence_id": "EV-BACKGROUND"}))
                self.assertEqual(evidence["result"]["data"]["reading_depth"], "summary_only")
                self.assertTrue(payload(await client.call_tool("get_provenance", {"record_id": "RS-SUMMARY-001"}))["result"]["records"])
                self.assertTrue(payload(await client.call_tool("check_source_freshness", {}))["result"]["evidence"])
                self.assertTrue((await client.call_tool("get_record", {"record_id": "MEM-001"})).isError)
                self.assertTrue((await client.call_tool("get_current_state", {"namespace": "../demo"})).isError)
                self.assertTrue((await client.call_tool("commit_demo_proposal", {"namespace": "real", "proposals": [], "validated_sha256": "x"})).isError)

    async def test_demo_validation_commit_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            demo = root / "spatial-unit-kb/local_tools/data/demo_working"
            demo.mkdir(parents=True)
            seed = Store(demo, "demo")
            seed.commit(build_demo(root, "A1"))
            resume(seed)
            proposals = [{"id": "Q-MCP-TEST", "kind": "OpenQuestion", "expected_version": 0, "category": "evaluation_injection",
                          "scope": "temporary MCP test", "refs": {}, "data": {"unresolved_target": "unknown", "why_unresolved": "test", "needed_evidence": "test"}}]
            params = StdioServerParameters(command=sys.executable, args=["-X", "utf8", str(HERE / "server.py"), "--workspace", str(root)])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    before = (demo / "records.json").read_bytes()
                    result = payload(await client.call_tool("validate_proposal", {"proposals": proposals}))["result"]
                    self.assertEqual(before, (demo / "records.json").read_bytes())
                    self.assertTrue((await client.call_tool("commit_demo_proposal", {"proposals": proposals, "validated_sha256": "wrong"})).isError)
                    args = {"proposals": proposals, "validated_sha256": result["proposal_sha256"]}
                    self.assertTrue(payload(await client.call_tool("commit_demo_proposal", args))["result"]["written"])
                    self.assertTrue((await client.call_tool("commit_demo_proposal", args)).isError)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    saved = payload(await client.call_tool("get_record", {"namespace": "demo", "record_id": "Q-MCP-TEST"}))
                    self.assertEqual(saved["result"]["version"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
