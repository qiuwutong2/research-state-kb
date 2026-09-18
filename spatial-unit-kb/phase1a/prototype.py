"""Deterministic sandbox demonstration; no model, simulation, or GIS execution."""
import argparse
import hashlib
import json
from pathlib import Path

from store import Store, proposal


def link(ident, version=1):
    return {"id": ident, "version": version}


def build_demo(workspace, outcome):
    records = []
    source_names = ["spatial_background_20260917", "restricted_shuffle_20260917"]
    for i, name in enumerate(source_names, 1):
        content = {"status": "synthetic_fixture", "conclusion": "Invented example, not a research finding."}
        records.append(proposal(f"EV-{i}", "Evidence", dict(
            sha256=hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest(),
            source=f"synthetic://{name}", locator="built-in synthetic fixture", content=content,
            reading_depth="synthetic fixture only",
            quality_limits="invented example; no real data or experiment")))
    records.append(proposal("RS-001", "ResearchState", dict(
        goal="区分空间背景与传播相关联系；先验证评价指标的辨别能力",
        known=["假想案例包含两种对照摘要"], unknown=["现有指标能否区分背景与相互作用"],
        assumptions=["所有案例内容均为合成测试数据"], constraints=["假想结果不写入真实项目", "不自动搜索区域"]),
        refs={"evidence": [link("EV-1"), link("EV-2")]}))
    records.append(proposal("H-001", "Hypothesis", dict(
        statement="真实候选空间表示包含传播相关时空信息",
        assumptions=["真实观测能够反映目标过程，尚需独立验证"], explains="真实数据中候选表示的过程意义", status="unresolved")))
    records.append(proposal("MC-EVAL-001", "MethodClaim", dict(
        statement="当前评价指标能区分背景平滑与相互作用恢复",
        assumptions=["生成场景与指标定义明确"], explains="为何较高得分可作为过程相关表示的证据", status="unresolved")))
    records.append(proposal("EXP-A", "Experiment", dict(
        question="指标能否区分 G0 无相互作用和 G1 已知相互作用？",
        design="预先指定模拟对照；本次只注入假想结果，没有执行模拟",
        controls=["共同评分支撑", "训练验证隔离", "记录匹配失败的边际"],
        metrics=["G0误报", "G1恢复", "不确定性"], status="designed_not_executed", outcomes=["A1", "A2", "A3"]),
        refs={"state": [link("RS-001")], "hypotheses": [link("H-001")], "method_claims": [link("MC-EVAL-001")]}))
    branches = {
        "A1": ("G0和G1均出现类似高恢复得分", "weakened", "修订指标", "这些场景中指标不能区分两种机制"),
        "A2": ("G0少误报且G1可恢复，敏感性场景保持区别", "supported_within_tested_scenarios", "核验真实观测机制", "仅支持所测试生成场景内的辨别能力"),
        "A3": ("G0与G1差异不清楚且区间很宽", "unresolved", "检查精度与可识别条件", "当前注入信息不足，不能判断机制不存在"),
    }
    pattern, after, choice, rationale = branches[outcome]
    reopening = {
        "A1": ["替换评价指标后能区分 G0/G1", "新生成器控制此前未建模差异"],
        "A2": ["新生成机制下辨别能力失效", "真实数据噪声或观测条件超出已测试范围"],
        "A3": ["增加有效重复后区间缩窄", "额外观测使竞争机制产生不同预测"],
    }[outcome]
    evidence_status = {
        "A1": "当前评价证据不能作为真实机制假设的支持路径",
        "A2": "仅支持模拟场景中的指标辨别能力，尚未提供真实机制证据",
        "A3": "识别能力仍不明确，当前证据不能更新真实机制判断",
    }[outcome]
    records.append(proposal("EV-INJECT", "Evidence", dict(
        source="predeclared branch in prototype.py; not measured data", locator=f"build_demo.branches.{outcome}",
        content=pattern, reading_depth="evaluation fixture", quality_limits="no real simulation run")))
    records.append(proposal("OBS-001", "Observation", dict(
        run_ref=f"DEMO-INJECTION-{outcome}", pattern=pattern, uncertainty="定性评测注入，无数值误差估计",
        artifact_ref="EV-INJECT@1"), refs={"experiment": [link("EXP-A")], "evidence": [link("EV-INJECT")]}))
    records.append(proposal("INT-001", "Interpretation", dict(
        compatible=["背景结构", "传播相关联系仍需另证"], excluded=[],
        assumptions=["只接受该假想分支定义"], limits="不证明真实广州传播存在或不存在；不赋予空间单元身份"),
        refs={"observations": [link("OBS-001")]}))
    records.append(proposal("BC-001", "BeliefChange", dict(
        target_kind="MethodClaim", before="unresolved", after=after, rationale=rationale,
        would_change_if=reopening),
        refs={"target": [link("MC-EVAL-001")], "interpretations": [link("INT-001")]}))
    method = next(r["data"].copy() for r in records if r["id"] == "MC-EVAL-001")
    method["status"] = after
    records.append(proposal("MC-EVAL-001", "MethodClaim", method, expected_version=1, refs={"changes": [link("BC-001")]}))
    records.append(proposal("BC-H-001", "BeliefChange", dict(
        target_kind="Hypothesis", before="unresolved", after="unresolved",
        rationale=evidence_status + "；不能据此推断真实传播机制成立或不存在。",
        evidence_status=evidence_status,
        would_change_if=["独立真实观测在明确识别条件下区分竞争机制"]),
        refs={"target": [link("H-001")], "interpretations": [link("INT-001")]}))
    science = next(r["data"].copy() for r in records if r["id"] == "H-001")
    science["evidence_status"] = evidence_status
    records.append(proposal("H-001", "Hypothesis", science, expected_version=1, refs={"changes": [link("BC-H-001")]}))
    records.append(proposal("DEC-001", "Decision", dict(
        options=["修订指标", "核验真实观测机制", "检查精度与可识别条件", "重复原配置"], choice=choice,
        rationale=rationale + "；未选择无条件重复原配置，因为没有新增识别信息。",
        stop_or_reopen_conditions=reopening),
        refs={"state": [link("RS-001")], "changes": [link("BC-001"), link("BC-H-001")]}))
    records.append(proposal("MEM-001", "ResearchMemory", dict(
        context=f"EXP-A 的 {outcome} 假想结果", lesson=rationale + "；" + evidence_status + "；重复实验须增加有效信息或改变识别条件。",
        exceptions=reopening + ["不外推到其他生成器、参数或真实传播"], retrieval_cues=["过程恢复", "背景平滑", outcome]),
        refs={"decisions": [link("DEC-001")], "results": [link("OBS-001")]}))
    state2 = records[2]["data"].copy()
    state2["known"] = state2["known"] + [f"评测沙盒注入 {outcome}，非真实结果"]
    records.append(proposal("RS-001", "ResearchState", state2, expected_version=1,
        refs={"evidence": [link("EV-1"), link("EV-2")], "decisions": [link("DEC-001")], "memory": [link("MEM-001")]}))
    return records


def render(store):
    records = store.records()
    lines = ["# Phase 1A 演示状态回放", "", "全部记录均在 demo 沙盒。分支解释由固定规则提供；不代表 Agent 推理通过。", "",
             f"记录数：{len(records)}；对象数：{len({r['id'] for r in records})}", "",
             "| 对象 | 版本 | 类型 | 来源/依赖 |", "|---|---|---|---|"]
    for r in records:
        refs = "; ".join(f"{role}: " + ", ".join(f"{x['id']}@{x['version']}" for x in links) for role, links in r["refs"].items())
        lines.append(f"| {r['id']} | {r['version']} | {r['kind']} | {refs} |")
    if any(r["id"] == "MC-EVAL-001" for r in records):
        lines += ["", "## 两类判断分别记录", "",
                  "| 对象 | 判断内容 | 当前状态 |", "|---|---|---|"]
        for ident in ("MC-EVAL-001", "H-001"):
            claim = store.get(ident)
            lines.append(f"| {ident} ({claim['kind']}) | {claim['data']['statement']} | {claim['data']['status']} |")
        lines += ["", "科学机制判断保持未决，变化的是方法判断及证据路径的适用性。", "",
                  "### 科学机制判断的保持记录", "", "```json",
                  json.dumps(store.get("BC-H-001")["data"], ensure_ascii=False, indent=2), "```"]
    lines += ["", "## 判断变更（具体目标见引用表）", "", "```json", json.dumps(store.get("BC-001")["data"], ensure_ascii=False, indent=2), "```",
              "", "## 当前决策", "", json.dumps(store.get("DEC-001")["data"], ensure_ascii=False, indent=2),
              "", "旧状态 RS-001@1 和旧假设 H-001@1 均保留。重新加载验证的是存储恢复，不是 D5 科研记忆验收。"]
    return "\n".join(lines) + "\n"


def resume(store):
    """Explicit rule-driven continuation, not an autonomous memory retrieval test."""
    previous = store.get("DEC-001")
    state = store.get("RS-001")
    return store.commit([proposal("DEC-002", "Decision", dict(
        options=previous["data"]["options"], choice=previous["data"]["choice"],
        rationale="确定性恢复示范：没有注入新证据，沿用 DEC-001 的有范围决策。",
        stop_or_reopen_conditions=previous["data"]["stop_or_reopen_conditions"]),
        refs={"state": [link(state["id"], state["version"])],
              "changes": previous["refs"]["changes"], "previous_decisions": [link("DEC-001")]} )])


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--outcome", choices=["A1", "A2", "A3"], default="A1")
    demo.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    demo.add_argument("--store", type=Path, required=True)
    show = sub.add_parser("inspect")
    show.add_argument("--store", type=Path, required=True)
    show.add_argument("--report", type=Path)
    continuation = sub.add_parser("resume")
    continuation.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    store = Store(args.store, "demo")
    if args.command == "demo":
        if store.records():
            parser.error("demo requires an empty store; use inspect to reload")
        store.commit(build_demo(args.workspace, args.outcome))
    elif args.command == "resume":
        resume(store)
    text = render(store)
    if args.command == "inspect" and args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
