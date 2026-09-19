"""Append-only experiment-route snapshots; reported history, not scientific certification."""
from pathlib import Path
import hashlib
import json
import math

from library import Library, MAX_BYTES, encoded, nonempty, require

FILE_EXTENSIONS = {".csv", ".tsv", ".json", ".txt", ".md", ".log", ".pdf", ".html", ".htm",
                   ".png", ".jpg", ".jpeg", ".svg", ".xlsx", ".parquet", ".npy"}
STATUSES = {"planned", "running", "completed", "failed", "paused", "abandoned"}
FIELDS = {"experiment_id", "title", "stage", "status", "goal", "method", "rationale", "parameters",
          "parents", "knowledge", "datasets", "artifacts", "change_reason", "summary", "open_questions"}


class Routes:
    def __init__(self, workspace, namespace="real"):
        self.lib = Library(workspace, namespace)

    def register_file(self, record_id, file_path, title, role, origin, expected_version=0):
        require(role in {"dataset", "artifact"}, "role must be dataset or artifact")
        require(nonempty(title) and nonempty(origin), "title and provenance origin required")
        path = Path(file_path)
        path = (path if path.is_absolute() else self.lib.workspace / path).resolve()
        require(path.is_relative_to(self.lib.workspace), "stage file inside workspace")
        require(path.is_file() and path.suffix.lower() in FILE_EXTENSIONS, "unsupported or missing file")
        require(0 < path.stat().st_size <= MAX_BYTES, "file must be 1 byte..50 MiB")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(0 < len(raw) <= MAX_BYTES, "file too large")
        digest = hashlib.sha256(raw).hexdigest()
        relative = "files/" + digest + path.suffix.lower()
        with self.lib.connection(True) as conn:
            count = conn.execute("SELECT MAX(version) FROM records WHERE id=?", (record_id,)).fetchone()[0] or 0
            require(type(expected_version) is int and expected_version >= 0 and count == expected_version, "stale version")
            if count:
                old = self.lib._get(conn, record_id)
                require(old["kind"] == "research_file" and old["data"]["role"] == role, "file role immutable")
            archive = self.lib.root / relative
            archive.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open("xb") as stream:
                    stream.write(raw)
            except FileExistsError:
                require(archive.read_bytes() == raw, "archive changed")
            data = {"title": title, "role": role, "origin": origin, "file": relative,
                    "sha256": digest, "bytes": len(raw), "original_filename": path.name,
                    "verification": "file archived; contents and reported execution not independently verified"}
            return self.lib._save(conn, record_id, "research_file", data, [], expected_version)

    def append(self, node_id, data):
        require(isinstance(data, dict) and set(data) == FIELDS, "missing or unexpected route fields")
        for key in FIELDS - {"parameters", "parents", "knowledge", "datasets", "artifacts"}:
            require(nonempty(data[key]), key + " must be nonempty text; state unknown explicitly")
        require(data["stage"] in {"start", "middle", "end"}, "invalid stage")
        require(data["status"] in STATUSES, "invalid status")
        require(isinstance(data["parameters"], dict), "parameters must be an object")
        encoded(data)  # rejects non-JSON numbers such as NaN; no invented parameter coercion
        require(all(nonempty(k) for k in data["parameters"]), "parameter keys required")
        for key in ("parents", "knowledge", "datasets", "artifacts"):
            require(isinstance(data[key], list), key + " must be a list")
        require(bool(data["knowledge"]), "knowledge references required; register a design note if original")
        require(bool(data["parents"]) or data["stage"] == "start", "non-start nodes need a parent")
        require(not data["parents"] or data["stage"] != "start", "start node cannot have parents")
        require(data["status"] not in {"completed", "failed"} or bool(data["artifacts"]),
                "reported completed/failed nodes require archived artifacts")
        all_refs = []
        with self.lib.connection(True) as conn:
            for key, kinds in (("parents", {"route_node"}), ("knowledge", {"source", "method", "formula"}),
                               ("datasets", {"research_file"}), ("artifacts", {"research_file"})):
                refs = data[key]
                require(len({encoded(r) for r in refs}) == len(refs), "duplicate references")
                if not refs:
                    continue
                targets = self.lib._references(conn, refs, kinds)
                for target in targets:
                    if key == "parents":
                        require(target["data"]["experiment_id"] == data["experiment_id"], "cross-experiment parent")
                    else:
                        if key in {"datasets", "artifacts"}:
                            require(target["data"]["role"] == ("dataset" if key == "datasets" else "artifact"),
                                    "wrong file role")
                        self.lib._trace(conn, target["id"], target["version"])
                for ref in refs:
                    if ref not in all_refs:
                        all_refs.append(ref)
            # Parents must already exist and every node is immutable, so forward edges/cycles are impossible.
            return self.lib._save(conn, node_id, "route_node", data, all_refs, 0)

    def graph(self, experiment_id=""):
        if not self.lib.db.exists():
            return {"namespace": self.lib.namespace, "experiments": [], "nodes": [], "edges": []}
        with self.lib.connection() as conn:
            rows = conn.execute("SELECT body,checksum FROM records WHERE kind='route_node' ORDER BY rowid").fetchall()
            nodes = [self.lib.decode(row) for row in rows]
            experiments = sorted({n["data"]["experiment_id"] for n in nodes})
            nodes = [n for n in nodes if not experiment_id or n["data"]["experiment_id"] == experiment_id]
            enriched = []
            for node in nodes:
                detail = dict(node)
                detail["citations"] = {}
                for group in ("knowledge", "datasets", "artifacts"):
                    items = []
                    for ref in node["data"][group]:
                        target = self.lib._get(conn, ref["id"], ref["version"])
                        items.append({"id": target["id"], "version": target["version"], "kind": target["kind"],
                                      "title": target["data"].get("title", target["id"]),
                                      "attribution": target["data"].get("origin", ""),
                                      "basis": target["data"].get("basis", ""),
                                      "content": target["data"].get("content", "")})
                    detail["citations"][group] = items
                enriched.append(detail)
        edges = [{"from": p["id"], "to": n["id"], "parent_version": p["version"]}
                 for n in nodes for p in n["data"]["parents"]]
        return {"namespace": self.lib.namespace, "experiments": experiments, "nodes": enriched, "edges": edges,
                "notice": "Reported snapshots. File references do not certify execution or scientific validity."}

    def compare(self, first_id, second_id):
        a, b = self.lib.get(first_id), self.lib.get(second_id)
        require(a["kind"] == b["kind"] == "route_node", "route nodes required")
        require(a["data"]["experiment_id"] == b["data"]["experiment_id"], "different experiments")
        changes = {}
        for key in sorted(FIELDS - {"experiment_id", "parents"}):
            if a["data"][key] != b["data"][key]:
                changes[key] = {"before": a["data"][key], "after": b["data"][key]}
        parameters = {}
        for key in sorted(a["data"]["parameters"].keys() | b["data"]["parameters"].keys()):
            before, after = a["data"]["parameters"], b["data"]["parameters"]
            if (key in before) != (key in after) or before.get(key) != after.get(key):
                parameters[key] = {"before_present": key in before, "before": before.get(key),
                                   "after_present": key in after, "after": after.get(key)}
        refs = {}
        for group in ("knowledge", "datasets", "artifacts"):
            before, after = a["data"][group], b["data"][group]
            refs[group] = {"added": [x for x in after if x not in before],
                           "removed": [x for x in before if x not in after]}
        return {"first": a["id"], "second": b["id"], "changes": changes,
                "parameter_changes": parameters, "reference_changes": refs}
