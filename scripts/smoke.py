#!/usr/bin/env python3
"""Installs the packaged plugin in rustgis-cli and runs it on RustGIS's World Atlas sample.

    python scripts/smoke.py [--cli path/to/rustgis-cli] [--strict]

Run scripts/package.py first. It installs dist/<id>-<version>.rgplugin in an empty plugins
folder, makes its Python environment (`rustgis-cli plugins prepare`, which downloads Python
and the requirements), and checks RustGIS lists its commands. Each tool runs with its
defaults (layer parameters get a sample layer of the right kind, field parameters one of its
fields) and must succeed. Each command that needs no parameters runs too; a failure there is
reported but only fails the run with --strict, since a command may need a selection or a
layer the sample doesn't have.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# A sample layer for each layer kind, and a field of it.
SAMPLE = {"polygonLayer": "Countries", "pointLayer": "Cities", "vectorLayer": "Countries", "layer": "Countries"}
FIELDS = {"field": "name", "numericField": "pop_est"}


def cli(exe: str, args: list[str], plugins_dir: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """Runs rustgis-cli with its own plugins folder.

    Args:
        exe: The rustgis-cli executable.
        args: Its arguments.
        plugins_dir: The plugins folder.
        timeout: Seconds before it is stopped.

    Returns:
        The finished process.
    """
    env = dict(os.environ, RUSTGIS_PLUGINS_DIR=plugins_dir)
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, env=env)


def run(exe: str, cmds: list[str], plugins_dir: str) -> subprocess.CompletedProcess:
    """Runs `cmds` on the sample project.

    Args:
        exe: The rustgis-cli executable.
        cmds: Commands, as `--cmd` takes them.
        plugins_dir: The plugins folder the plugin is installed in.

    Returns:
        The finished process.
    """
    args = ["run", "--sample"]
    for c in cmds:
        args += ["--cmd", c]
    return cli(exe, args, plugins_dir)


def main() -> int:
    """Installs the plugin and runs its tools and commands.

    Returns:
        The exit status: 1 when anything failed.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cli", default=os.environ.get("RUSTGIS_CLI") or shutil.which("rustgis-cli") or "rustgis-cli")
    ap.add_argument("--strict", action="store_true", help="fail when a command fails too")
    args = ap.parse_args()
    manifest = json.loads((ROOT / "plugin" / "plugin.json").read_text(encoding="utf-8"))
    plugin_id = manifest["id"]
    package = ROOT / "dist" / f"{plugin_id}-{manifest['version']}.rgplugin"
    if not package.is_file():
        print(f"error: no {package.relative_to(ROOT)}: run python scripts/package.py first", file=sys.stderr)
        return 1
    failures = 0
    with tempfile.TemporaryDirectory() as plugins_dir:
        for step in (["plugins", "install", str(package)], ["plugins", "prepare", plugin_id]):
            r = cli(args.cli, step, plugins_dir, timeout=1800)
            if r.returncode != 0:
                print(f"error: rustgis-cli {' '.join(step[:2])} failed:\n{r.stderr}")
                return 1
        listed = run(args.cli, ["info.commands"], plugins_dir)
        if listed.returncode != 0:
            print(f"error: RustGIS couldn't load the plugin:\n{listed.stderr}")
            return 1
        ids = {c["id"] for c in json.loads(listed.stdout)}
        for c in manifest.get("commands", []):
            cid = f"plugin:{plugin_id}/{c['id']}"
            if cid not in ids:
                print(f"error: {cid} isn't listed")
                failures += 1
                continue
            params = c.get("params", "{}")
            if params not in ("{}", "") and ":" in params and "?" not in params:
                print(f"   command {c['id']}: skipped (it needs parameters)")
                continue
            r = run(args.cli, [cid], plugins_dir)
            if r.returncode == 0:
                print(f"   command {c['id']}: ok")
            else:
                print(f"{'error' if args.strict else 'warning'}: command {c['id']} failed: {r.stderr.strip()}")
                failures += args.strict
        for t in manifest.get("tools", []):
            params, skip = {}, False
            for p in t.get("params", []):
                if p["kind"] in SAMPLE:
                    params[p["name"]] = SAMPLE[p["kind"]]
                elif p["kind"] in FIELDS:
                    params[p["name"]] = FIELDS[p["kind"]]
                elif p.get("required") and "default" not in p:
                    skip = True
            if skip:
                print(f"   tool {t['id']}: skipped (a required parameter has no default)")
                continue
            r = run(args.cli, ["gp.run=" + json.dumps({"tool": f"plugin:{plugin_id}/{t['id']}", "params": params})], plugins_dir)
            if r.returncode == 0:
                print(f"   tool {t['id']}: ok")
            else:
                print(f"error: tool {t['id']} failed: {r.stderr.strip()}")
                failures += 1
    print(f"{failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
