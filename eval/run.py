"""Golden-set evaluation launcher. The runner lives in the API (`app/evaluation.py`) because it
runs the real agent; this script only starts it with the API's Python environment.

Usage: python eval/run.py [golden.jsonl] [--live] [--today YYYY-MM-DD] [--json out.json]
Same as `make eval` (pass extra flags with EVAL_ARGS="--live").
"""

import shutil
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "apps" / "api"


def main(argv: list[str]) -> int:
    venv = API / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    if shutil.which("uv"):
        command = ["uv", "run", "python"]
    elif venv.with_suffix(".exe").exists() or venv.exists():
        command = [str(venv)]
    else:
        print("Install the API environment first: make install", file=sys.stderr)
        return 2
    # The runner starts in apps/api, so make path arguments absolute from the caller's directory.
    args: list[str] = []
    for index, arg in enumerate(argv[1:]):
        after_path_flag = index > 0 and argv[index] in ("--json", "--seed-dir")
        is_path = arg.endswith(".jsonl") or after_path_flag
        args.append(str(Path(arg).resolve()) if is_path else arg)
    return subprocess.run([*command, "-m", "app.evaluation", *args], cwd=API, check=False).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
