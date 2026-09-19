"""Synthetic classifications for the existing route demo; never touches real."""
from pathlib import Path
import sys
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "spatial-unit-kb/local_tools"))
from knowledge_map import KnowledgeMap
from route_demo import build_demo

def build_knowledge_demo(root):
    build_demo(root)
    atlas=KnowledgeMap(root,"demo")
    graph=atlas.graph()
    for node in graph["nodes"]:
        if node["classification"]:
            continue
        ident=node["id"]
        labels=(["描述统计","实验设计"] if ident=="SRC-ROUTE-A" else
                ["稳健性分析","实验设计"] if ident=="SRC-ROUTE-B" else
                ["数据管理"] if node["kind"]=="research_file" else
                ["实验设计","稳健性分析"])
        atlas.classify({"id":ident,"version":node["version"]},labels,
                       "合成教学案例中的人工分类；不是论文内容或真实研究结论。")
    return atlas.graph()

if __name__=="__main__":
    graph=build_knowledge_demo(ROOT)
    print(json.dumps({"namespace":"demo","nodes":len(graph["nodes"]),"domains":len(graph["domains"]),
                      "url":"http://127.0.0.1:8765/knowledge?namespace=demo"},ensure_ascii=False))
