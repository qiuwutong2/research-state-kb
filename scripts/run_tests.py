"""Run independent suites in fresh interpreters without private data."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
for suite in ("phase1a", "local_tools", "mcp_server"):
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", "unittest",
        "discover", "-s", str(ROOT / "spatial-unit-kb" / suite), "-p", "test_*.py", "-v"], cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
print("All suites passed.")
