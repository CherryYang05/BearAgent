import json
import subprocess
import sys


def test_python_module_entrypoint_runs_doctor() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "bearagent", "doctor", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
