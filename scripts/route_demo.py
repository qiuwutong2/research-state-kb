"""Create a synthetic branching route; never imports or alters real research data."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "spatial-unit-kb/local_tools"))
from routes import Routes

def build_demo(root):
    routes = Routes(root, "demo")
    lib = routes.lib
    folder = Path(root) / "spatial-unit-kb/data/route_demo_inputs"
    folder.mkdir(parents=True, exist_ok=True)
    notes = [
        ("SRC-ROUTE-A", "均值描述：教学方法笔记", "算术均值描述同单位可比测量的样本中心，不识别机制。", "项目教学示例作者；并非已发表论文"),
        ("SRC-ROUTE-B", "稳健性与敏感性：教学思路笔记", "看到极端值时保留完整结果，并比较数据处理规则的敏感性，不只报告有利结果。", "项目教学示例作者；并非已发表论文"),
    ]
    existing = {r["id"] for r in lib.list(limit=250)["records"]}
    for ident,title,content,origin in notes:
        path = folder / (ident + ".md")
        if not path.exists():
            path.write_text("# "+title+"\n\n合成教学材料，不是真实研究证据。\n\n"+content,encoding="utf-8")
        if ident not in existing:
            lib.register_source(ident,str(path),title,"user_note",origin)
    for ident,name,role,content in [
        ("DATA-ROUTE-A","样本测量 v1","dataset","sample,value\nA,1\nB,2\nC,3\n"),
        ("DATA-ROUTE-B","补充测量 v2","dataset","sample,value\nA,1\nB,2\nC,3\nD,10\n"),
        ("ART-ROUTE-END","教学阶段总结","artifact","# 教学阶段总结\n这是预制的演示文件，没有执行实验。\n展示资料补充后保留完整结果和敏感性路线的记录方式。\n")]:
        path=folder/(ident+(".md" if role=="artifact" else ".csv"))
        if not path.exists(): path.write_text(content,encoding="utf-8")
        if ident not in existing: routes.register_file(ident,str(path),name,role,"本仓库合成教学文件；未执行真实实验")
    def ref(ident): return {"id":ident,"version":1}
    base={"experiment_id":"DEMO-ROUTE","title":"定义目标与初始方案","stage":"start","status":"planned",
          "goal":"描述样本测量，并识别方法选择带来的变化。","method":"描述性均值",
          "rationale":"参考均值教学笔记；先明确数据含义和单位。",
          "parameters":{"missing_policy":"report","summary":"mean","threshold":None},
          "parents":[],"knowledge":[ref("SRC-ROUTE-A")],"datasets":[ref("DATA-ROUTE-A")],"artifacts":[],
          "change_reason":"建立初始路线，尚未执行实验。","summary":"计划快照。","open_questions":"还缺哪些观测条件？"}
    nodes=[("ROUTE-START",base)]
    middle=copy.deepcopy(base);middle.update(title="补充数据与方法依据",stage="middle",parents=[ref("ROUTE-START")],
        method="均值描述与敏感性对照",rationale="加入稳健性思路；保持全部数据作为主分析。",
        knowledge=[ref("SRC-ROUTE-A"),ref("SRC-ROUTE-B")],datasets=[ref("DATA-ROUTE-B")],
        change_reason="补充数据出现不同取值范围，新增教学方法依据以讨论处理规则。")
    nodes.append(("ROUTE-UPDATE",middle))
    branch=copy.deepcopy(middle);branch.update(title="路线 A：保留全部观测",parents=[ref("ROUTE-UPDATE")],
        parameters={"missing_policy":"report","summary":"mean","sensitivity":"with_and_without_extremes"},
        change_reason="保留原始观测，同时规划敏感性对照。",summary="尚未执行，保留计划与条件。")
    nodes.append(("ROUTE-BRANCH-A",branch))
    abandoned=copy.deepcopy(middle);abandoned.update(title="路线 B：仅删去极端值",status="abandoned",parents=[ref("ROUTE-UPDATE")],
        parameters={"summary":"mean","threshold":5},change_reason="只保留处理后的结果不足以说明敏感性，故本路线不采用。",
        summary="记录曾考虑过的路线，便于回溯，不抹去历史。")
    nodes.append(("ROUTE-BRANCH-B",abandoned))
    end=copy.deepcopy(branch);end.update(title="阶段总结与后续问题",stage="end",status="completed",parents=[ref("ROUTE-BRANCH-A")],
        artifacts=[ref("ART-ROUTE-END")],change_reason="演示如何归档阶段总结；不是实际计算结果。",
        summary="合成示例：以预制教学文件展示完成状态。没有执行科学实验。",
        open_questions="真实使用时必须关联实际运行产物，并继续核对适用条件。")
    nodes.append(("ROUTE-END",end))
    for ident,data in nodes:
        if ident not in existing: routes.append(ident,data)
    return routes.graph("DEMO-ROUTE")

if __name__=="__main__":
    graph=build_demo(ROOT)
    print(json.dumps({"namespace":"demo","nodes":len(graph["nodes"]),"edges":len(graph["edges"]),
                      "open":"http://127.0.0.1:8765/?namespace=demo",
                      "note":"Synthetic only. Start scripts/route_viewer.py separately."},ensure_ascii=False))
