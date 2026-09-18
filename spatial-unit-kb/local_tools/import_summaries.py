"""Import two bounded project summaries, never raw case data or experimental results."""
import argparse
import hashlib
import json
from pathlib import Path

from research_kb import Store, IntegrityError, latest, validate_batch

SOURCES = [
    ("EV-BACKGROUND", "experiments/spatial_background_20260917/state.json"),
    ("EV-SHUFFLE", "experiments/restricted_shuffle_20260917/state.json"),
]
ALLOWED = {"status", "conclusion", "next_decision", "CP_identity_assigned",
           "recent_pairing_increment_not_robustly_separated",
           "support_range_information_not_reduced_to_random_points"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def make(ident, kind, data, refs, version, category="project_summary"):
    return dict(id=ident, kind=kind, data=data, refs=refs, scope="两个指定项目状态摘要的导入视图；非全项目实时状态",
                category=category, expected_version=version)


def plan(workspace, store):
    if store.namespace != "real":
        raise IntegrityError("summary import requires real namespace")
    existing = {r["id"]: r for r in latest(store.records())}
    batch, snapshots, evidence = [], {}, []
    for ident, relative in SOURCES:
        source = (workspace / relative).resolve()
        if not source.is_relative_to(workspace.resolve()):
            raise IntegrityError("source escapes workspace")
        raw = source.read_bytes()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("status"), str):
            raise IntegrityError("summary requires a status string")
        selected = {k: parsed[k] for k in sorted(ALLOWED) if k in parsed}
        checksum = digest(raw)
        previous = existing.get(ident)
        version = previous["version"] if previous else 0
        if not previous or previous["data"].get("sha256") != checksum:
            # Store only allowlisted summary fields, never arbitrary new source fields.
            snapshot = json.dumps(selected, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            snapshot_hash = digest(snapshot)
            relative_snapshot = f"sources/{snapshot_hash}.json"
            snapshots[relative_snapshot] = snapshot
            data = dict(source=str(source), locator="state.json allowlisted summary fields", content=selected,
                        reading_depth="summary_only", quality_limits="未读完整报告、未复算；此证据记录来源报告的表述，不认证科学结论",
                        sha256=checksum, snapshot=relative_snapshot, snapshot_sha256=snapshot_hash)
            batch.append(make(ident, "Evidence", data, {}, version))
            version += 1
        evidence.append({"id": ident, "version": version})
    if not batch:
        return [], {}
    old_state = existing.get("RS-SUMMARY-001")
    state_version = old_state["version"] if old_state else 0
    state_data = dict(
        goal="恢复指定摘要中的研究进展与未决问题，为后续核验证据提供入口",
        known=[{"source_ref": e, "statement": "该来源报告了研究状态；原文见Evidence.content，不提升为本轮独立验证的实验事实"} for e in evidence],
        unknown=["完整报告与摘要是否一致", "现有观测是否可区分传播过程与观测机制", "两份摘要之后是否存在其他更新"],
        assumptions=["源文件是待核验的项目记录，不是自动认证的研究事实"],
        constraints=["保留摘要证据层级", "未赋予新的空间单元身份", "不开放真实实验结果和判断转移", "不是全项目最新状态证明"],
        interpretations=[], observations=[], open_questions=["Q-SUMMARY-001"])
    batch.append(make("RS-SUMMARY-001", "ResearchState", state_data, {"evidence": evidence}, state_version))
    old_question = existing.get("Q-SUMMARY-001")
    question_data = dict(unresolved_target="来源摘要是否足以支持下一步研究选择",
                         why_unresolved="仅登记摘要，尚未核对原报告、运行产物及后续状态",
                         needed_evidence="核对报告与运行登记；查明独立位置/报告机制证据是否可用",
                         status="open", candidate_next_steps=["核对已有报告与摘要", "登记可用的独立观测资料"],
                         decision_status="proposed_not_accepted")
    batch.append(make("Q-SUMMARY-001", "OpenQuestion", question_data,
                      {"evidence": evidence, "state": [{"id": "RS-SUMMARY-001", "version": state_version + 1}]},
                      old_question["version"] if old_question else 0, "analysis"))
    validate_batch(store, batch)
    return batch, snapshots


def import_summaries(workspace, store, commit=False):
    batch, snapshots = plan(workspace, store)
    result = {"changed": bool(batch), "written": False, "proposals": batch,
              "scope": "summary registration only; no Observation/Decision/BeliefChange"}
    if commit and batch:
        for relative, raw in snapshots.items():
            path = store.directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("xb") as stream:
                    stream.write(raw)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise IntegrityError("snapshot collision or corruption")
        result["records"] = store.commit(batch, actor="local-summary-importer (summary_only)")
        result["written"] = True
    return result


def check_sources(workspace, store):
    output = []
    for evidence in latest(store.records()):
        if evidence["kind"] != "Evidence":
            continue
        data = evidence["data"]
        if "snapshot" not in data or "sha256" not in data:
            output.append({"id": evidence["id"], "status": "uncheckable"})
            continue
        source = Path(data["source"]).resolve()
        snapshot = (store.directory / data["snapshot"]).resolve()
        if not source.is_relative_to(workspace.resolve()) or not snapshot.is_relative_to((store.directory / "sources").resolve()):
            raise IntegrityError("source/snapshot outside permitted roots")
        output.append({"id": evidence["id"], "version": evidence["version"],
                       "source_status": "missing" if not source.is_file() else "unchanged" if digest(source.read_bytes()) == data["sha256"] else "changed",
                       "snapshot_status": "missing" if not snapshot.is_file() else "valid" if digest(snapshot.read_bytes()) == data["snapshot_sha256"] else "corrupt"})
    return {"evidence": output, "scientific_validity": "not evaluated"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["import", "check-sources"])
    p.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--commit", action="store_true")
    args = p.parse_args()
    store = Store(args.store, "real")
    try:
        if args.command == "check-sources":
            if not store.path.is_file():
                raise IntegrityError("store missing")
            result = check_sources(args.workspace, store)
        else:
            result = import_summaries(args.workspace, store, args.commit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({"ok": False, "error": "导入或核验失败；请检查源文件、存储和版本。"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
