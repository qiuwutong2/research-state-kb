"""No-model local CLI. Reasoning belongs to Codex; this tool only handles records."""
from __future__ import annotations

import argparse
import copy
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase1a"))
from store import Store, FIELDS, IntegrityError, fingerprint


def latest(records):
    return list({r["id"]: r for r in records}.values())


def select(store, kind=None, history=False):
    records = store.records()
    return [r for r in (records if history else latest(records)) if kind is None or r["kind"] == kind]


def search(store, query, kind=None, history=False, limit=20):
    terms = unicodedata.normalize("NFKC", query).casefold().split()
    if not terms:
        raise IntegrityError("query must contain a keyword")
    if not 1 <= limit <= 100:
        raise IntegrityError("limit must be 1..100")
    found = []
    for record in select(store, kind, history):
        text = unicodedata.normalize("NFKC", json.dumps(
            {k: record[k] for k in ("id", "kind", "scope", "data")}, ensure_ascii=False)).casefold()
        if all(term in text for term in terms):
            found.append(record)
    return {"total_matches": len(found), "records": found[:limit],
            "retrieval": "NFKC casefold substring AND; no embeddings or semantic ranking"}


def provenance(store, ident, version=None):
    records = store.records()
    index = {(r["id"], r["version"]): r for r in records}
    candidates = [r for r in records if r["id"] == ident and (version is None or r["version"] == version)]
    if not candidates:
        raise IntegrityError("object not found")
    start = candidates[-1]
    queue, seen, output = [(start["id"], start["version"])], set(), []
    while queue:
        key = queue.pop(0)
        if key in seen:
            continue
        seen.add(key)
        r = index[key]
        output.append(r)
        queue.extend((ref["id"], ref["version"]) for links in r["refs"].values() for ref in links)
    return {"root": {"id": start["id"], "version": start["version"]}, "records": output,
            "note": "reference traversal only; does not independently verify source files or scientific validity"}


def validate_batch(store, proposals):
    """Validate in memory, against the same constraints used by commit."""
    if not isinstance(proposals, list) or not proposals:
        raise IntegrityError("proposal file must be a nonempty list")
    state = store._read()
    if state["format"] != 2:
        raise IntegrityError("legacy stores are read-only")
    records = copy.deepcopy(state["records"])
    keys = {"id", "kind", "data", "refs", "scope", "category", "expected_version"}
    for p in proposals:
        if not isinstance(p, dict) or set(p) != keys:
            raise IntegrityError("proposal must have exactly the documented fields")
        expected = p["expected_version"]
        if type(expected) is not int or expected < 0:
            raise IntegrityError("expected_version must be a nonnegative integer")
        if expected != sum(r["id"] == p["id"] for r in records):
            raise IntegrityError("stale expected_version")
        r = {k: copy.deepcopy(v) for k, v in p.items() if k != "expected_version"}
        r.update(namespace=store.namespace, version=expected + 1)
        store._validate(r, records)
        records.append(r)
    return {"structurally_valid": True, "proposal_count": len(proposals),
            "proposal_sha256": fingerprint(proposals), "written": False,
            "note": "scientific content is not evaluated; commit rechecks versions"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--namespace", choices=["demo", "real"], default="demo")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-demo")
    init.add_argument("--seed", type=Path, required=True)
    current = sub.add_parser("state")
    current.add_argument("--id")
    get = sub.add_parser("get")
    get.add_argument("id")
    get.add_argument("--version", type=int)
    listing = sub.add_parser("list")
    listing.add_argument("--kind", choices=list(FIELDS))
    listing.add_argument("--history", action="store_true")
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--kind", choices=list(FIELDS))
    find.add_argument("--history", action="store_true")
    find.add_argument("--limit", type=int, default=20)
    trail = sub.add_parser("provenance")
    trail.add_argument("id")
    trail.add_argument("--version", type=int)
    sub.add_parser("validate")
    add = sub.add_parser("submit")
    add.add_argument("--file", type=Path, required=True)
    add.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    store = Store(args.store, args.namespace)
    try:
        if args.command == "init-demo":
            if args.namespace != "demo":
                raise IntegrityError("init-demo cannot initialize real data")
            seed = Store(args.seed, "demo")
            records = seed.records()
            if not records or seed._read()["format"] != 2:
                raise IntegrityError("seed must be an existing format-2 demo")
            raw = seed.path.read_bytes()
            args.store.mkdir(parents=True, exist_ok=False)
            with store.path.open("xb") as stream:
                stream.write(raw)
            result = {"initialized": True, "records": len(records), "namespace": "demo"}
        else:
            if not store.path.is_file():
                raise IntegrityError("store does not exist; initialize explicitly")
            if args.command == "state":
                states = select(store, "ResearchState")
                if args.id:
                    states = [r for r in states if r["id"] == args.id]
                if len(states) != 1:
                    raise IntegrityError("state is missing or ambiguous; specify --id")
                result = states[0]
            elif args.command == "get":
                result = store.get(args.id, args.version)
            elif args.command == "list":
                result = select(store, args.kind, args.history)
            elif args.command == "search":
                result = search(store, args.query, args.kind, args.history, args.limit)
            elif args.command == "provenance":
                result = provenance(store, args.id, args.version)
            elif args.command == "validate":
                records = store.records()
                result = {"structurally_valid": True, "records": len(records),
                          "scientific_validity": "not evaluated", "namespace": store.namespace}
            elif args.command == "submit":
                proposals = json.loads(args.file.read_text(encoding="utf-8-sig"))
                result = validate_batch(store, proposals)
                if args.commit:
                    saved = store.commit(proposals, actor="codex-local-cli (unverified caller label)")
                    result.update(written=True, records=saved)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        # Avoid echoing arbitrary user input or local data through exception strings.
        print(json.dumps({"ok": False, "error": "操作未完成：检查存储、字段、版本、引用类型及命名空间；未验证科学内容。"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
