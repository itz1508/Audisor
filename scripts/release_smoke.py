from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def _python(venv_root: Path) -> Path:
    return venv_root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a clean Audisor wheel installation and public fixture.")
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        environment = Path(directory) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = _python(environment)
        subprocess.run([str(python), "-m", "pip", "--disable-pip-version-check", "-q", "install", str(args.wheel.resolve())], check=True)
        version = subprocess.run([str(python), "-m", "audisor.cli", "--version"], check=True, capture_output=True, text=True)
        output = Path(directory) / "demo-output"
        demo = subprocess.run([str(python), str(args.repository_root / "scripts" / "run_demo.py"), "--output-root", str(output)], check=True, capture_output=True, text=True)
        summary = json.loads(demo.stdout)
    if version.stdout.strip() != "audisor-local 0.9.0" or summary.get("status") != "completed":
        raise SystemExit("release_smoke_failed")
    print(json.dumps({"status": "completed", "wheel": args.wheel.name, "demo": summary}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
