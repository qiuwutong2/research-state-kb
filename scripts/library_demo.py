"""One synthetic source -> formula -> experiment draft -> archived-file trace."""
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "spatial-unit-kb/local_tools"))
from library import Library

lib = Library(ROOT, "demo")
fixture = json.loads((ROOT / "examples/library_tutorial.json").read_text(encoding="utf-8"))
existing = {r["id"] for r in lib.list(limit=250)["records"]}
if "SRC-TUTORIAL" not in existing:
    lib.register_source("SRC-TUTORIAL", "examples/tutorial_note.md", "Synthetic descriptive-statistics note", "user_note")
if "FORM-TUTORIAL" not in existing:
    lib.save_card("FORM-TUTORIAL", "formula", fixture["formula"], [{"id":"SRC-TUTORIAL","version":1}])
if "PLAN-TUTORIAL" not in existing:
    lib.save_plan("PLAN-TUTORIAL", fixture["plan"])
trace = lib.trace("PLAN-TUTORIAL", 1)
print(json.dumps({"namespace":"demo","plan":"PLAN-TUTORIAL@1","status":"draft_unverified",
                  "files":trace["files"],"note":"Synthetic tutorial only. No experiment was run."}, ensure_ascii=False, indent=2))
