#!/usr/bin/env python3
"""Checks the plugin as the registry will, and packages it.

    python scripts/package.py                 # check, package into dist/
    python scripts/package.py --tag v0.1.0    # also check the tag matches plugin.json's version

It writes:

    dist/<id>-<version>.rgplugin  the package: every file in plugin/ (but caches), to attach
                                  to a release
    dist/<id>.json                the registry entry to submit (registry/<id>.json)

The manifest checks are those of the registry's own scripts/build.py, downloaded from
opengeos/rustgis-plugins (--offline skips them).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin"
DIST = ROOT / "dist"
BUILD_PY = "https://raw.githubusercontent.com/opengeos/rustgis-plugins/main/scripts/build.py"
# A fixed timestamp, so the same files make the same package (and SHA-256).
ZIP_TIME = (2024, 1, 1, 0, 0, 0)
# Left out of the package: caches and editor files.
SKIP = re.compile(r"(^|/)(__pycache__|\.pytest_cache|\.ruff_cache|\.venv|\.DS_Store)(/|$)|\.py[co]$")
MAX_PACKAGE = 64 * 1024 * 1024
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
PYTHON_RE = re.compile(r"^3\.\d+(\.\d+)?$")
PLATFORMS = {"windows", "macos", "linux", "default"}


def registry_checks():
    """The registry's scripts/build.py, as a module.

    Returns:
        The module, or None when it can't be downloaded.
    """
    path = DIST / ".registry-build.py"
    try:
        with urllib.request.urlopen(BUILD_PY, timeout=30) as r:  # noqa: S310 - a fixed https address
            DIST.mkdir(exist_ok=True)
            path.write_bytes(r.read())
    except OSError as e:
        if not path.is_file():
            print(f"warning: can't download the registry's checks ({e}); skipping them", file=sys.stderr)
            return None
    spec = importlib.util.spec_from_file_location("registry_build", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_process(manifest: dict, files: set[str]) -> list[str]:
    """What RustGIS needs of a process plugin's manifest and files.

    Args:
        manifest: plugin.json.
        files: The package's file names.

    Returns:
        The problems found.
    """
    problems = []
    if manifest.get("runtime") != "process":
        problems.append('plugin.json needs "runtime": "process"')
    run = manifest.get("run")
    argvs = list(run.values()) if isinstance(run, dict) else [run]
    if isinstance(run, dict) and not set(run) <= PLATFORMS:
        problems.append(f"run's platforms are {sorted(PLATFORMS)}")
    for argv in argvs:
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
            problems.append('run must be a program and its arguments, ["python", "main.py"]')
            continue
        # The script python runs, or a program in the plugin's folder, must be in the package.
        for a in argv[1:2] if argv[0] in ("python", "python3") else argv[:1]:
            if ("/" in a or a.endswith(".py")) and a not in files:
                problems.append(f"run names {a}, which isn't in plugin/")
    python = manifest.get("python")
    if python is not None:
        if not isinstance(python, dict) or not PYTHON_RE.match(str(python.get("version", ""))):
            problems.append('python must be {"version": "3.12", "requirements": "requirements.txt"}')
        elif python.get("requirements") and python["requirements"] not in files:
            problems.append(f"python.requirements names {python['requirements']}, which isn't in plugin/")
    if not VERSION_RE.match(str(manifest.get("version", ""))):
        problems.append("version must look like 1.0.0")
    return problems


def package(files: list[Path]) -> bytes:
    """A reproducible .rgplugin: the files at the root of a zip archive, in a fixed order.

    Args:
        files: The files in plugin/.

    Returns:
        The package's bytes.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            info = zipfile.ZipInfo(f.relative_to(PLUGIN).as_posix(), ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            # Executables stay executable when RustGIS unpacks them.
            info.external_attr = (0o755 if os.access(f, os.X_OK) else 0o644) << 16
            z.writestr(info, f.read_bytes())
    return buf.getvalue()


def main() -> int:
    """Checks and packages the plugin.

    Returns:
        The exit status: 1 when a check failed.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="a release tag (v1.2.3) that must match plugin.json's version")
    ap.add_argument("--url", help="where the package will be downloaded from (default: the GitHub release's asset)")
    ap.add_argument("--offline", action="store_true", help="skip the registry's checks")
    args = ap.parse_args()

    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    plugin_id, version = manifest.get("id", ""), manifest.get("version", "")
    files = sorted(f for f in PLUGIN.rglob("*") if f.is_file() and not SKIP.search(f.relative_to(PLUGIN).as_posix()))
    names = {f.relative_to(PLUGIN).as_posix() for f in files}
    problems = check_process(manifest, names)
    if args.tag and args.tag.removeprefix("v") != version:
        problems.append(f"the tag {args.tag} doesn't match plugin.json's version {version} (tag v{version})")

    checks = None if args.offline else registry_checks()
    if checks:
        where = f"{plugin_id} {version}"
        checks.check_manifest(manifest, where)
        for name in ("check_tab", "check_panel"):
            if hasattr(checks, name):
                getattr(checks, name)(manifest, where)
        problems += checks.problems
        checks.problems.clear()
    data = package(files)
    if len(data) > MAX_PACKAGE:
        problems.append(f"the package is {len(data):,} bytes, more than 64 MB")
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 1

    DIST.mkdir(exist_ok=True)
    name = f"{plugin_id}-{version}.rgplugin"
    (DIST / name).write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo and re.match(r"^https://github\.com/[^/]+/[^/]+$", manifest.get("homepage", "")):
        repo = manifest["homepage"].removeprefix("https://github.com/")
    url = args.url or (f"https://github.com/{repo}/releases/download/v{version}/{name}" if repo else f"https://<where you publish it>/{name}")
    entry = {"id": plugin_id, "source": {"url": url, "sha256": sha}, "categories": ["Utilities"]}
    (DIST / f"{plugin_id}.json").write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")

    print(f"dist/{name}  {len(data):,} bytes  sha256 {sha}")
    print("  " + ", ".join(sorted(names)))
    print(f"dist/{plugin_id}.json  the registry entry (set its categories before you submit it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
