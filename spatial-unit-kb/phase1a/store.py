"""Small, framework-independent, versioned research record store.

Only structural integrity is checked here. Scientific validity requires review.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FIELDS = {
    "ResearchState": {"goal", "known", "unknown", "assumptions", "constraints"},
    "Evidence": {"source", "locator", "content", "reading_depth", "quality_limits"},
    "Hypothesis": {"statement", "assumptions", "explains", "status"},
    "MethodClaim": {"statement", "assumptions", "explains", "status"},
    "Experiment": {"question", "design", "controls", "metrics", "status", "outcomes"},
    "Observation": {"run_ref", "pattern", "uncertainty", "artifact_ref"},
    "Interpretation": {"compatible", "excluded", "assumptions", "limits"},
    "BeliefChange": {"before", "after", "rationale", "would_change_if"},
    "Decision": {"options", "choice", "rationale", "stop_or_reopen_conditions"},
    "ResearchMemory": {"context", "lesson", "exceptions", "retrieval_cues"},
    "OpenQuestion": {"unresolved_target", "why_unresolved", "needed_evidence"},
}
# Required role, target kind. Values are lists to allow several observations.
ROLES = {
    "ResearchState": {"evidence": "Evidence"},
    "Hypothesis": {},
    "MethodClaim": {},
    "Evidence": {},
    "Experiment": {"state": "ResearchState", "hypotheses": "Hypothesis"},
    "Observation": {"experiment": "Experiment", "evidence": "Evidence"},
    "Interpretation": {"observations": "Observation"},
    "BeliefChange": {"target": ("Hypothesis", "MethodClaim"), "interpretations": "Interpretation"},
    "Decision": {"state": "ResearchState", "changes": "BeliefChange"},
    "ResearchMemory": {"decisions": "Decision", "results": "Observation"},
    "OpenQuestion": {},
}
OPTIONAL_ROLES = {
    "OpenQuestion": {"evidence": "Evidence", "state": "ResearchState"},
    "ResearchState": {"decisions": "Decision", "memory": "ResearchMemory"},
    "Hypothesis": {"changes": "BeliefChange", "evidence": "Evidence"},
    "MethodClaim": {"changes": "BeliefChange", "evidence": "Evidence"},
    "Experiment": {"method_claims": "MethodClaim"},
    "Decision": {"previous_decisions": "Decision"},
}
CATEGORIES = {"project_summary", "source_evidence", "analysis", "design", "evaluation_injection"}


class IntegrityError(ValueError):
    pass


class ConflictError(IntegrityError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def ref(record):
    return {"id": record["id"], "version": record["version"]}


def proposal(ident, kind, data, *, refs=None, scope="GRT-001 sandbox", category="evaluation_injection", expected_version=0):
    return dict(id=ident, kind=kind, data=data, refs=refs or {}, scope=scope,
                category=category, expected_version=expected_version)


class Store:
    """One namespace per store; commits replace a complete snapshot atomically.

    Local single-writer lock. A stale lock requires manual inspection; it is never
    silently removed. Hashes detect accidental edits, not malicious rewriting.
    """
    def __init__(self, directory, namespace):
        if namespace not in {"demo", "real"}:
            raise IntegrityError("namespace must be demo or real")
        self.directory = Path(directory)
        self.namespace = namespace
        self.path = self.directory / "records.json"

    def _read(self):
        if not self.path.exists():
            return {"format": 2, "namespace": self.namespace, "records": []}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if state["format"] not in {1, 2} or state["namespace"] != self.namespace:
                raise IntegrityError("store format/namespace mismatch")
            prior = []
            for record in state["records"]:
                body = {k: v for k, v in record.items() if k != "hash"}
                if record["hash"] != fingerprint(body):
                    raise IntegrityError("record checksum mismatch")
                if record["prev_hash"] != (prior[-1]["hash"] if prior else None):
                    raise IntegrityError("broken history chain")
                self._validate(record, prior, strict=state["format"] == 2)
                prior.append(record)
            return state
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise IntegrityError("invalid store structure") from exc

    def records(self):
        return copy.deepcopy(self._read()["records"])

    def get(self, ident, version=None):
        found = [r for r in self.records() if r["id"] == ident and (version is None or r["version"] == version)]
        if not found:
            raise IntegrityError(f"record not found: {ident}@{version}")
        return found[-1]

    def _validate(self, record, prior, strict=True):
        kind = record["kind"]
        if kind not in FIELDS or not re.fullmatch(r"[A-Z][A-Z0-9-]*", record["id"]):
            raise IntegrityError("invalid kind or id")
        if record["namespace"] != self.namespace:
            raise IntegrityError("cross-namespace record")
        if not isinstance(record["scope"], str) or not record["scope"].strip():
            raise IntegrityError("scope required")
        if record["category"] not in CATEGORIES:
            raise IntegrityError("unknown provenance category")
        if self.namespace == "demo" and record["category"] != "evaluation_injection":
            raise IntegrityError("demo records must remain evaluation_injection")
        if self.namespace == "real" and record["category"] == "evaluation_injection":
            raise IntegrityError("evaluation data forbidden in real namespace")
        # Phase 1A does not certify or ingest real experimental observations.
        if self.namespace == "real" and kind in {"Observation", "Interpretation", "BeliefChange", "Decision", "ResearchMemory"}:
            raise IntegrityError("real research transitions are not enabled in Phase 1A")
        history = [r for r in prior if r["id"] == record["id"]]
        if record["version"] != len(history) + 1:
            raise ConflictError("nonsequential version")
        if history and history[-1]["kind"] != kind:
            raise IntegrityError("object kind is immutable")
        data = record["data"]
        if not isinstance(data, dict) or FIELDS[kind] - data.keys():
            raise IntegrityError(f"missing fields for {kind}")
        if any(data[k] is None or data[k] == "" for k in FIELDS[kind]):
            raise IntegrityError("required values may not be null/empty strings; state unknown explicitly")
        roles = record["refs"]
        allowed = ROLES[kind] | OPTIONAL_ROLES.get(kind, {})
        if not isinstance(roles, dict) or set(roles) - allowed.keys():
            raise IntegrityError("unknown reference role")
        resolved = {}
        for role, target_kind in allowed.items():
            links = roles.get(role, [])
            if not isinstance(links, list) or (role in ROLES[kind] and not links):
                raise IntegrityError(f"required reference: {role}")
            resolved[role] = []
            for link in links:
                if not isinstance(link, dict) or set(link) != {"id", "version"}:
                    raise IntegrityError("references require exact id and version")
                targets = [r for r in prior if r["id"] == link["id"] and r["version"] == link["version"]]
                target_kinds = target_kind if isinstance(target_kind, tuple) else (target_kind,)
                if not targets or targets[0]["kind"] not in target_kinds:
                    raise IntegrityError(f"missing or wrong-kind reference: {role}")
                resolved[role].append(targets[0])
        if kind == "BeliefChange":
            if len(resolved["target"]) != 1 or data["before"] != resolved["target"][0]["data"]["status"]:
                raise IntegrityError("belief before must match exact target version")
            if strict and data.get("target_kind") != resolved["target"][0]["kind"]:
                raise IntegrityError("belief target_kind must match target; method and mechanism are distinct")
        if kind in {"Hypothesis", "MethodClaim"} and history:
            changes = resolved.get("changes", [])
            old = history[-1]
            if not changes or not any(c["data"]["after"] == data["status"] and c["refs"]["target"] == [ref(old)] for c in changes):
                raise IntegrityError("claim revision requires matching BeliefChange")
            if strict and any(data[key] != old["data"][key] for key in ("statement", "assumptions", "explains")):
                raise IntegrityError("claim meaning is immutable; create a new object for a different claim")
        if kind == "Observation" and self.namespace == "demo":
            if not data["run_ref"].startswith("DEMO-INJECTION-"):
                raise IntegrityError("demo observation requires explicit injection run marker")
        if kind == "Decision" and data["choice"] not in data["options"]:
            raise IntegrityError("decision choice must be one of the recorded alternatives")

    def commit(self, proposals, *, actor="phase1a deterministic prototype"):
        if not proposals:
            raise IntegrityError("empty transaction")
        if not isinstance(actor, str) or not actor.strip():
            raise IntegrityError("actor label required")
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = self.directory / ".writer.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ConflictError("store locked; inspect active writer before retry") from exc
        os.close(fd)
        temporary = None
        try:
            state = self._read()
            if state["format"] == 1:
                raise IntegrityError("legacy v0.1 store is read-only; create a separate v0.2 sandbox")
            added = []
            for item in proposals:
                item = copy.deepcopy(item)
                expected = item.pop("expected_version")
                history = [r for r in state["records"] if r["id"] == item["id"]]
                if expected != len(history):
                    raise ConflictError(f"stale expected_version for {item['id']}")
                record = dict(item, namespace=self.namespace, version=expected + 1,
                              recorded_at=datetime.now(timezone.utc).isoformat(),
                              actor=actor,
                              prev_hash=state["records"][-1]["hash"] if state["records"] else None)
                self._validate(record, state["records"])
                record["hash"] = fingerprint(record)
                state["records"].append(record)
                added.append(record)
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded(state))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            return copy.deepcopy(added)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
            lock.unlink()
