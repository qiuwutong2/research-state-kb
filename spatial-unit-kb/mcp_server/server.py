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
from library import Library
from routes import Routes

Namespace = Literal["real", "demo"]
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def build_server(workspace: Path):
    workspace = workspace.resolve()
    kb = workspace / "spatial-unit-kb"
    roots = {"real": kb / "data/real_summary", "demo": kb / "local_tools/data/demo_working"}
    mcp = FastMCP("research-kb", instructions="Local deterministic knowledge tools. Legacy real research state is read-only. Domain sources and draft cards/plans may be recorded when authorized; no real experimental conclusions. Demo records are not real evidence.")

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


    def library(namespace):
        return Library(workspace, namespace)

    @mcp.tool(annotations=READ)
    def library_status(namespace: Namespace = "real") -> dict:
        """Inspect the small domain library without creating it. Counts are not scientific readiness."""
        return library(namespace).status()

    @mcp.tool(annotations=WRITE)
    def register_source(source_id: str, file_path: str, title: str,
                        source_type: Literal["paper", "book", "web", "user_note"] = "paper",
                        origin: str = "", expected_version: int = 0, namespace: Namespace = "real") -> dict:
        """Archive a user-authorized local file staged inside workspace (e.g. inbox/).
        Registers file provenance only; does not read, parse or certify scientific content.
        Web input requires a saved local snapshot and original URL. No downloads.
        """
        return library(namespace).register_source(source_id, file_path, title, source_type, origin, expected_version)

    @mcp.tool(annotations=READ)
    def search_knowledge(query: str = "", kind: str = "", limit: int = 50, namespace: Namespace = "real") -> dict:
        """List or keyword-search source metadata, method/formula cards and experiment drafts.
        kind: source, method, formula, experiment_plan, research_file, route_node, or empty. Does not search PDF full text.
        """
        return {"namespace": namespace, **library(namespace).list(query, kind, limit)}

    @mcp.tool(annotations=READ)
    def get_knowledge(record_id: str, version: int | None = None, namespace: Namespace = "real") -> dict:
        """Read a domain-library record; separate from legacy get_record and its research-state store."""
        return library(namespace).get(record_id, version)

    @mcp.tool(annotations=READ)
    def trace_knowledge(record_id: str, version: int | None = None, namespace: Namespace = "real") -> dict:
        """Trace exact references to archived source files and verify their hashes. Page numbers optional."""
        return library(namespace).trace(record_id, version)

    @mcp.tool(annotations=WRITE)
    def save_knowledge_card(card_id: str, kind: Literal["method", "formula"], data: dict,
                            sources: list[dict], expected_version: int = 0, namespace: Namespace = "real") -> dict:
        """Save an authorized draft method/formula card. Sources must be exact source id/version refs.
        Required data: title, content, conditions, limitations, basis(direct/adapted/original), rationale.
        Formula adds expression and symbols dict; method adds procedure. Optional locator, reading_note.
        Does not verify scientific correctness or record accepted experimental conclusions.
        """
        return library(namespace).save_card(card_id, kind, data, sources, expected_version)

    @mcp.tool(annotations=WRITE)
    def save_experiment_plan(plan_id: str, data: dict, expected_version: int = 0, namespace: Namespace = "real") -> dict:
        """Save an authorized draft, never an executed experiment or accepted Decision.
        data: title, question, data_requirements, alternatives, steps, outputs, interpretation_limits.
        Each step: action, purpose, basis(direct/adapted/original), rationale, refs[{id,version}].
        Every step needs source/method/formula refs that resolve to archived files.
        """
        return library(namespace).save_plan(plan_id, data, expected_version)


    @mcp.tool(annotations=WRITE)
    def register_research_file(record_id: str, file_path: str, title: str,
                               role: Literal["dataset", "artifact"], origin: str,
                               expected_version: int = 0, namespace: Namespace = "real") -> dict:
        """Archive authorized local dataset/result/log for route discussion. File existence is not execution verification."""
        return Routes(workspace, namespace).register_file(record_id, file_path, title, role, origin, expected_version)

    @mcp.tool(annotations=WRITE)
    def append_route_node(node_id: str, data: dict, namespace: Namespace = "real") -> dict:
        """Append immutable route snapshot. Never overwrite nodes; corrections create child nodes.
        Required data: experiment_id,title,stage(start/middle/end),status(planned/running/completed/failed/paused/abandoned),
        goal,method,rationale,parameters(dict),parents,knowledge,datasets,artifacts (exact id/version lists),
        change_reason,summary,open_questions. Knowledge nonempty; completed/failed require artifacts.
        Status is reported by caller, not independently verified. Does not update accepted scientific conclusions.
        """
        return Routes(workspace, namespace).append(node_id, data)

    @mcp.tool(annotations=READ)
    def get_route_graph(experiment_id: str = "", namespace: Namespace = "real") -> dict:
        """Read experiment route branches with fixed source/file versions; no silent demo fallback."""
        return Routes(workspace, namespace).graph(experiment_id)

    @mcp.tool(annotations=READ)
    def compare_route_nodes(first_id: str, second_id: str, namespace: Namespace = "real") -> dict:
        """Compare goals, methods, per-key parameters and added/removed source, dataset and artifact references."""
        return Routes(workspace, namespace).compare(first_id, second_id)

    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    build_server(parser.parse_args().workspace).run(transport="stdio")
