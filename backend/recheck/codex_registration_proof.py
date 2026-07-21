"""Codex registration proof script.

Proves `audisor install-codex` against an isolated CODEX_HOME environment:
  - Codex executable (codex.cmd) is locatable
  - audisor install-codex adds audisor MCP entry pointing to installed interpreter/module
  - Preserves unrelated existing MCP entries
  - Running install-codex twice is idempotent (no duplicate entry)
  - User's real Codex configuration remains untouched throughout

Design notes:
  - Codex CLI rejects CODEX_HOME values under %TEMP% with exit code 1 and refuses to
    write helper binaries. The isolated home is therefore created under AppData\\Local.
  - npm PATH must include codex.cmd but must NOT include a shadowing npm `audisor` package.
    We resolve the absolute path to codex.cmd before building the subprocess env.
  - The proof runs against the editable source installation (the current .venv) rather
    than an isolated clean venv, because the clean-install proof is the
    responsibility of clean_installed_mcp_proof.py. This proof focuses on the
    install-codex command shape and CODEX_HOME isolation.
"""
from __future__ import annotations

import json
from pathlib import Path
import os
import shutil
import subprocess
import sys


# Persistent but isolated: not inside the repo, not inside %TEMP%
ISOLATED_CODEX_HOME = Path("C:/Users/itz15/AppData/Local/audisor_proof/codex_home")
REAL_CODEX_CONFIG = Path("C:/Users/itz15/.codex/config.toml")
NPM_BIN = Path(r"C:\Users\itz15\AppData\Roaming\npm")
CODEX_CMD = NPM_BIN / "codex.cmd"


def _resolve_codex() -> tuple[bool, str]:
    """Return (found, path) for the codex CLI executable."""
    if CODEX_CMD.exists():
        return True, str(CODEX_CMD)
    # Fallback: search PATH
    import shutil as sh
    found = sh.which("codex")
    return bool(found), found or ""


def main() -> int:
    codex_found, codex_path = _resolve_codex()

    # ------------------------------------------------------------------ setup
    # Wipe any leftover state so the run is clean
    if ISOLATED_CODEX_HOME.exists():
        shutil.rmtree(str(ISOLATED_CODEX_HOME))
    ISOLATED_CODEX_HOME.mkdir(parents=True, exist_ok=True)

    config_path = ISOLATED_CODEX_HOME / "config.toml"
    initial_config = (
        '[mcp_servers.aflow]\n'
        'command = "uv"\n'
        'args = ["run", "--directory", "D:/Dev/Aflow_cli", "aflow", "mcp"]\n\n'
        '[mcp_servers.openaiDeveloperDocs]\n'
        'url = "https://developers.openai.com/mcp"\n'
    )
    config_path.write_text(initial_config, encoding="utf-8")

    # Build env: put NPM_BIN first so codex.cmd is found before any shadowing package,
    # and put it ahead of any other npm-based audisor shim.
    env = os.environ.copy()
    env["CODEX_HOME"] = str(ISOLATED_CODEX_HOME)
    # Ensure codex.cmd's directory is first in PATH, ahead of anything that might shadow it.
    current_path = env.get("PATH", "")
    # Remove any prior occurrence of NPM_BIN to avoid doubling
    cleaned = ";".join(
        p for p in current_path.split(";") if p and Path(p) != NPM_BIN
    )
    env["PATH"] = str(NPM_BIN) + ";" + cleaned

    # Use the current editable-install audisor (sys.executable's environment)
    # rather than building a second isolated venv — the clean-install proof
    # already verifies the wheel. Use the venv's audisor binary.
    venv_scripts = Path(sys.executable).parent
    audisor_bin = venv_scripts / "audisor.exe" if sys.platform == "win32" else venv_scripts / "audisor"

    # Snapshot real config before any test run
    real_before = REAL_CODEX_CONFIG.read_bytes() if REAL_CODEX_CONFIG.exists() else None

    # ---------------------------------------------------------------- run 1
    res1 = subprocess.run(
        [str(audisor_bin), "install-codex", "--json"],
        capture_output=True, text=True, env=env,
    )
    install_1_ok = res1.returncode == 0

    content_1 = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    audisor_entry_added = "[mcp_servers.audisor]" in content_1
    unrelated_entry_preserved = (
        "aflow" in content_1
        and "D:/Dev/Aflow_cli" in content_1
        and "openaiDeveloperDocs" in content_1
    )
    # install-codex writes sys.executable as the interpreter
    interpreter_points_to_installed = (
        str(sys.executable).replace("\\", "/") in content_1.replace("\\", "/")
        or "audisor.cli" in content_1
    )

    # ---------------------------------------------------------------- run 2 (idempotency)
    res2 = subprocess.run(
        [str(audisor_bin), "install-codex", "--json"],
        capture_output=True, text=True, env=env,
    )
    install_2_ok = res2.returncode == 0

    content_2 = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    audisor_section_count = content_2.count("[mcp_servers.audisor]")
    idempotent_no_duplicate = audisor_section_count == 1

    # Snapshot real config after test runs
    real_after = REAL_CODEX_CONFIG.read_bytes() if REAL_CODEX_CONFIG.exists() else None
    real_codex_untouched = real_before == real_after

    # ---------------------------------------------------------------- cleanup
    shutil.rmtree(str(ISOLATED_CODEX_HOME))

    # ---------------------------------------------------------------- report
    report = {
        "codex_executable_found": codex_found,
        "codex_path": codex_path,
        "isolated_codex_home": str(ISOLATED_CODEX_HOME),
        "install_first_run_ok": install_1_ok,
        "audisor_entry_added": audisor_entry_added,
        "unrelated_entry_preserved": unrelated_entry_preserved,
        "interpreter_points_to_installed": interpreter_points_to_installed,
        "install_second_run_ok": install_2_ok,
        "idempotent_no_duplicate": idempotent_no_duplicate,
        "real_codex_config_untouched": real_codex_untouched,
        "res1_stdout": res1.stdout.strip(),
        "res2_stdout": res2.stdout.strip(),
    }
    report["all_checks_passed"] = bool(
        report["codex_executable_found"]
        and report["install_first_run_ok"]
        and report["audisor_entry_added"]
        and report["unrelated_entry_preserved"]
        and report["interpreter_points_to_installed"]
        and report["install_second_run_ok"]
        and report["idempotent_no_duplicate"]
        and report["real_codex_config_untouched"]
    )

    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
