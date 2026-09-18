"""Local STDIO MCP adapter. No LLM, network client, or scientific inference."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_tools"))
from research_kb import Store, IntegrityError, select, search, provenance, validate_batch, fingerprint
from import_summaries import check_sources

Namespace = Literal["real", "demo"]
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def build_server(workspace: Path):
    workspace = workspace.resolve()
    kb = workspace / "spatial-unit-kb"
    roots = {"real": kb / "data/real_summary", "demo": kb / "local_tools/data/demo_working"}
    mcp = FastMCP("research-kb", instructions="Local deterministic knowledge tools. Real store is read-only through MCP. Demo records are not real evidence.")

    def store(namespace):
        path = roots[namespace]
        if not path.resolve().is_relative_to(kb.resolve()):
            raise IntegrityError("store must stay within configured KB")
        result = Store(path, namespace)
        if not result.path.is_file():
            raise IntegrityError("configured store missing")
        return result

    def envelope(namespace, result):
        return {"namespace": namespace, "store": str(roots[namespace]), "result": result,
                "scientific_validity": "not evaluated"}

    @mcp.tool(annotations=READ)
    def get_current_state(namespace: Namespace = "real", state_id: str | None = None) -> dict:
        """Read latest ResearchState. Real covers only imported summaries, not the full project."""
        states = select(store(namespace), "ResearchState")
        if state_id:
            states = [r for r in states if r["id"] == state_id]
        if len(states) != 1:
            raise ValueError("state missing or ambiguous; provide state_id")
        return envelope(namespace, states[0])

    @mcp.tool(annotations=READ)
    def get_open_questions(namespace: Namespace = "real") -> dict:
        """Read latest OpenQuestion records. Empty means no registered questions."""
        return envelope(namespace, select(store(namespace), "OpenQuestion"))

    @mcp.tool(annotations=READ)
    def get_record(record_id: str, namespace: Namespace = "real", version: int | None = None) -> dict:
        """Read an exact or latest object version (Hypothesis, MethodClaim, Experiment, etc.)."""
        return envelope(namespace, store(namespace).get(record_id, version))

    @mcp.tool(annotations=READ)
    def get_evidence(evidence_id: str, namespace: Namespace = "real", version: int | None = None) -> dict:
        """Read registered Evidence, including reading depth and original-source hashes."""
        record = store(namespace).get(evidence_id, version)
        if record["kind"] != "Evidence":
            raise ValueError("requested record is not Evidence")
        return envelope(namespace, record)

    @mcp.tool(annotations=READ)
    def get_provenance(record_id: str, namespace: Namespace = "real", version: int | None = None) -> dict:
        """Traverse exact version references; not independent scientific verification."""
        return envelope(namespace, provenance(store(namespace), record_id, version))

    @mcp.tool(annotations=READ)
    def get_decisions(namespace: Namespace = "real", include_history: bool = False) -> dict:
        """Read Decision records; never substitute demo records when real history is empty."""
        return envelope(namespace, select(store(namespace), "Decision", include_history))

    @mcp.tool(annotations=READ)
    def get_research_memory(namespace: Namespace = "real") -> dict:
        """Read registered latest ResearchMemory; an empty real store is not a failure."""
        return envelope(namespace, select(store(namespace), "ResearchMemory"))

    @mcp.tool(annotations=READ)
    def find_evidence(query: str, namespace: Namespace = "real", limit: int = 20) -> dict:
        """Keyword AND substring search of Evidence only; no embeddings or semantic ranking."""
        return envelope(namespace, search(store(namespace), query, "Evidence", limit=limit))

    @mcp.tool(annotations=READ)
    def search_research_memory(query: str, namespace: Namespace = "real", limit: int = 20) -> dict:
        """Keyword search of ResearchMemory, including scope and exceptions."""
        return envelope(namespace, search(store(namespace), query, "ResearchMemory", limit=limit))

    @mcp.tool(annotations=READ)
    def validate_state(namespace: Namespace = "real") -> dict:
        """Check hashes, versions, reference types and namespace; does not judge research claims."""
        records = store(namespace).records()
        return envelope(namespace, {"structurally_valid": True, "records": len(records)})

    @mcp.tool(annotations=READ)
    def check_source_freshness() -> dict:
        """Compare two real summary source hashes and stored snapshot hashes. No source import."""
        return envelope("real", check_sources(workspace, store("real")))

    @mcp.tool(annotations=READ)
    def validate_proposal(proposals: list[dict], namespace: Namespace = "demo") -> dict:
        """Dry-run a batch of complete proposal objects; writes nothing. Real transition restrictions apply."""
        return envelope(namespace, validate_batch(store(namespace), proposals))

    @mcp.tool(annotations=WRITE)
    def commit_demo_proposal(proposals: list[dict], validated_sha256: str, namespace: Namespace = "demo") -> dict:
        """Commit only an explicitly authorized demo batch matching its validation hash. Real writes disabled."""
        if namespace != "demo":
            raise ValueError("real writes are not exposed through MCP")
        if validated_sha256 != fingerprint(proposals):
            raise ValueError("proposal differs from validated batch")
        target = store(namespace)
        validate_batch(target, proposals)
        records = target.commit(proposals, actor="research-kb MCP caller (unverified label)")
        return envelope(namespace, {"written": True, "records": records})

    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    build_server(parser.parse_args().workspace).run(transport="stdio")
