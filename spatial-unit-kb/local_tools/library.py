"""Small project library: source files, knowledge cards and experiment drafts.
Standard library only. No extraction, inference or execution of source contents.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

KINDS = {"source", "method", "formula", "experiment_plan", "research_file", "route_node"}
EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".epub"}
MAX_BYTES = 50 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Library:
    def __init__(self, workspace, namespace="real"):
        require(namespace in {"real", "demo"}, "invalid namespace")
        self.workspace = Path(workspace).resolve()
        self.namespace = namespace
        self.root = self.workspace / "spatial-unit-kb/data/library" / namespace
        require(self.root.resolve().is_relative_to(self.workspace), "library escapes workspace")
        self.db = self.root / "library.sqlite3"

    @contextmanager
    def connection(self, write=False):
        if write:
            self.root.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db, timeout=15)
        else:
            require(self.db.is_file(), "library not initialized")
            conn = sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=15)
        try:
            if write:
                conn.execute("CREATE TABLE IF NOT EXISTS records (id TEXT, version INTEGER, kind TEXT, body TEXT, checksum TEXT, PRIMARY KEY(id,version))")
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def decode(self, row):
        require(row is not None, "record not found")
        body, checksum = row
        require(hashlib.sha256(body.encode()).hexdigest() == checksum, "record checksum mismatch")
        record = json.loads(body)
        require(record["namespace"] == self.namespace, "namespace mismatch")
        return record

    def _get(self, conn, ident, version=None):
        if version is None:
            row = conn.execute("SELECT body,checksum FROM records WHERE id=? ORDER BY version DESC LIMIT 1", (ident,)).fetchone()
        else:
            require(type(version) is int and version > 0, "version must be positive")
            row = conn.execute("SELECT body,checksum FROM records WHERE id=? AND version=?", (ident, version)).fetchone()
        return self.decode(row)

    def get(self, ident, version=None):
        with self.connection() as conn:
            return self._get(conn, ident, version)

    def list(self, query="", kind="", limit=50):
        require(kind == "" or kind in KINDS, "invalid kind")
        require(type(limit) is int and 1 <= limit <= 250, "limit must be 1..250")
        if not self.db.exists():
            return {"records": [], "total_matches": 0}
        terms = unicodedata.normalize("NFKC", query).casefold().split()
        with self.connection() as conn:
            rows = conn.execute("SELECT r.body,r.checksum FROM records r JOIN (SELECT id,MAX(version) v FROM records GROUP BY id) x ON r.id=x.id AND r.version=x.v ORDER BY r.id").fetchall()
        found = []
        for row in rows:
            record = self.decode(row)
            text = unicodedata.normalize("NFKC", encoded(record)).casefold()
            if (not kind or record["kind"] == kind) and all(t in text for t in terms):
                found.append(record)
        return {"records": found[:limit], "total_matches": len(found)}

    def status(self):
        counts = {k: self.list(kind=k, limit=1)["total_matches"] for k in sorted(KINDS)}
        return {"namespace": self.namespace, "initialized": self.db.exists(), "counts": counts,
                "scale_note": "Designed for approximately 200 sources, not a hard cap.",
                "scientific_readiness": "not evaluated; source coverage is not method applicability"}

    def _references(self, conn, refs, allowed):
        require(isinstance(refs, list) and bool(refs), "at least one reference required")
        targets = []
        for ref in refs:
            require(isinstance(ref, dict) and set(ref) == {"id", "version"}, "refs require exact id/version")
            require(nonempty(ref["id"]) and type(ref["version"]) is int and ref["version"] > 0, "invalid reference")
            target = self._get(conn, ref["id"], ref["version"])
            require(target["kind"] in allowed, "wrong reference kind")
            targets.append(target)
        return targets

    def _trace(self, conn, ident, version=None):
        pending = [self._get(conn, ident, version)]
        records, seen, files = [], set(), []
        while pending:
            record = pending.pop()
            key = (record["id"], record["version"])
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if record["kind"] in {"source", "research_file"}:
                relative = record["data"]["file"]
                path = (self.root / relative).resolve()
                require(path.is_relative_to((self.root / "files").resolve()), "archive path escapes root")
                require(path.is_file(), "archived source missing")
                require(hashlib.sha256(path.read_bytes()).hexdigest() == record["data"]["sha256"], "archived source changed")
                files.append({"source_id": record["id"], "version": record["version"],
                              "title": record["data"]["title"], "path": str(path),
                              "sha256": record["data"]["sha256"], "file_verified": True})
            for ref in record["refs"]:
                pending.append(self._get(conn, ref["id"], ref["version"]))
        return {"namespace": self.namespace, "records": records, "files": files,
                "scientific_validity": "not evaluated; files and references only"}

    def trace(self, ident, version=None):
        with self.connection() as conn:
            return self._trace(conn, ident, version)

    def _save(self, conn, ident, kind, data, refs, expected):
        require(isinstance(ident, str) and re.fullmatch(r"[A-Z][A-Z0-9-]{0,79}", ident), "invalid ID")
        require(type(expected) is int and expected >= 0, "expected_version must be nonnegative")
        previous = conn.execute("SELECT MAX(version) FROM records WHERE id=?", (ident,)).fetchone()[0] or 0
        require(previous == expected, "stale expected_version")
        if previous:
            require(self._get(conn, ident)["kind"] == kind, "record kind is immutable")
        record = {"id": ident, "version": expected + 1, "namespace": self.namespace, "kind": kind,
                  "data": data, "refs": refs, "record_status": ("source_registered" if kind == "source" else "reported_not_independently_verified" if kind in {"research_file", "route_node"} else "draft_unverified"),
                  "created_at": datetime.now(timezone.utc).isoformat()}
        body = encoded(record)
        conn.execute("INSERT INTO records VALUES (?,?,?,?,?)",
                     (ident, expected + 1, kind, body, hashlib.sha256(body.encode()).hexdigest()))
        return record

    def register_source(self, source_id, file_path, title, source_type="paper", origin="", expected_version=0):
        require(nonempty(title), "title required")
        require(source_type in {"paper", "book", "web", "user_note"}, "invalid source type")
        require(isinstance(origin, str), "origin must be text")
        require(source_type != "web" or origin.startswith(("https://", "http://")), "web snapshot requires original URL")
        path = Path(file_path)
        path = (path if path.is_absolute() else self.workspace / path).resolve()
        require(path.is_relative_to(self.workspace), "stage source inside workspace/inbox first")
        require(path.is_file() and path.suffix.lower() in EXTENSIONS, "unsupported or missing source file")
        require(0 < path.stat().st_size <= MAX_BYTES, "source size must be 1 byte..50 MiB")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(0 < len(raw) <= MAX_BYTES, "source too large")
        checksum = hashlib.sha256(raw).hexdigest()
        relative = "files/" + checksum + path.suffix.lower()
        with self.connection(True) as conn:
            # Check version before writing an archive; a failed DB write may leave an unreferenced immutable file.
            prior = conn.execute("SELECT MAX(version) FROM records WHERE id=?", (source_id,)).fetchone()[0] or 0
            require(type(expected_version) is int and prior == expected_version, "stale expected_version")
            dest = self.root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                with dest.open("xb") as stream:
                    stream.write(raw)
            except FileExistsError:
                require(dest.read_bytes() == raw, "archive collision or corruption")
            data = {"title": title, "source_type": source_type, "origin": origin, "original_filename": path.name,
                    "file": relative, "sha256": checksum, "bytes": len(raw),
                    "reading_depth": "not_assessed", "locator": None}
            return self._save(conn, source_id, "source", data, [], expected_version)

    def save_card(self, card_id, kind, data, sources, expected_version=0):
        require(kind in {"method", "formula"}, "kind must be method or formula")
        require(isinstance(data, dict), "data must be an object")
        required = {"title", "content", "conditions", "limitations", "basis", "rationale"}
        required |= {"expression", "symbols"} if kind == "formula" else {"procedure"}
        optional = {"locator", "reading_note"}
        require(required <= data.keys() and data.keys() <= required | optional, "unexpected or missing card fields")
        for key in required - {"symbols"}:
            require(nonempty(data[key]), key + " must be nonempty text")
        if kind == "formula":
            require(isinstance(data["symbols"], dict) and data["symbols"] and all(nonempty(k) and nonempty(v) for k, v in data["symbols"].items()), "symbols must explain each named variable")
        require(data["basis"] in {"direct", "adapted", "original"}, "invalid basis")
        with self.connection(True) as conn:
            targets = self._references(conn, sources, {"source"})
            for target in targets:
                self._trace(conn, target["id"], target["version"])
            return self._save(conn, card_id, kind, data, sources, expected_version)

    def save_plan(self, plan_id, data, expected_version=0):
        require(isinstance(data, dict), "data must be an object")
        fields = {"title", "question", "data_requirements", "alternatives", "steps", "outputs", "interpretation_limits"}
        require(set(data) == fields, "unexpected or missing plan fields")
        for key in fields - {"steps"}:
            require(nonempty(data[key]), key + " must be nonempty text")
        require(isinstance(data["steps"], list) and data["steps"], "steps required")
        refs = []
        with self.connection(True) as conn:
            for step in data["steps"]:
                require(isinstance(step, dict) and set(step) == {"action", "purpose", "basis", "rationale", "refs"}, "invalid step fields")
                for key in {"action", "purpose", "basis", "rationale"}:
                    require(nonempty(step[key]), "step text required")
                require(step["basis"] in {"direct", "adapted", "original"}, "invalid step basis")
                targets = self._references(conn, step["refs"], {"source", "method", "formula"})
                for target in targets:
                    self._trace(conn, target["id"], target["version"])
                for ref in step["refs"]:
                    if ref not in refs:
                        refs.append(ref)
            return self._save(conn, plan_id, "experiment_plan", data, refs, expected_version)
