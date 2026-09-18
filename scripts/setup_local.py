"""Configure this checkout with the current interpreter; never overwrite stores."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "spatial-unit-kb/phase1a"))
from store import Store
from prototype import build_demo, resume

def main():
    config = ROOT / ".codex/config.toml"
    if config.exists():
        raise SystemExit("Config exists. Merge the research-kb entry manually; no files changed.")
    import mcp  # fail early if the selected interpreter lacks dependencies
    demo = Store(ROOT / "spatial-unit-kb/local_tools/data/demo_working", "demo")
    if not demo.path.exists():
        demo.commit(build_demo(ROOT, "A1"))
        resume(demo)
    else:
        demo.records()
    quote = lambda value: json.dumps(str(value), ensure_ascii=False)
    config.parent.mkdir(parents=True, exist_ok=True)
    content = ("[mcp_servers.research-kb]\ncommand = " + quote(sys.executable)
               + "\nargs = [\"-X\", \"utf8\", " + quote(ROOT / "spatial-unit-kb/mcp_server/server.py")
               + ", \"--workspace\", " + quote(ROOT) + "]\ncwd = " + quote(ROOT)
               + "\nstartup_timeout_sec = 30\ntool_timeout_sec = 30\nenabled = true\n")
    with config.open("x", encoding="utf-8") as stream:
        stream.write(content)
    print("Configured local MCP and synthetic demo. Real store was not created.")
    print(config)

if __name__ == "__main__":
    main()
