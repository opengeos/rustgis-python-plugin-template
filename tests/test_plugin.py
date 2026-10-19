"""Runs the plugin in plugin/ against a stand-in for RustGIS (tests/fake_rustgis.py).

These tests run whatever plugin/ holds: each command must answer, and each tool must run on
two sample countries. Add tests of your own plugin's behaviour below them.
"""

from __future__ import annotations

import pytest
from fake_rustgis import COUNTRIES, MANIFEST, PluginCallError, call_plugin

COMMANDS = [c["id"] for c in MANIFEST.get("commands", [])]
TOOLS = MANIFEST.get("tools", [])
FIELDS = {"field": "name", "numericField": "pop_est"}


@pytest.mark.parametrize("command", COMMANDS)
def test_each_command_answers(command):
    try:
        call_plugin({"kind": "command", "id": command})
    except PluginCallError as e:
        # A command may need a selection or data the stand-in doesn't have; it must say so.
        assert str(e)


@pytest.mark.parametrize("tool", TOOLS, ids=[t["id"] for t in TOOLS])
def test_each_tool_runs(tool):
    params = {}
    for p in tool.get("params", []):
        if p["kind"] in ("layer", "vectorLayer", "polygonLayer"):
            params[p["name"]] = "Countries"
        elif p["kind"] in FIELDS:
            params[p["name"]] = FIELDS[p["kind"]]
        elif "default" in p:
            params[p["name"]] = p["default"]
    result, calls = call_plugin({"kind": "tool", "id": tool["id"], "params": params, "layers": {"Countries": COUNTRIES}})
    assert isinstance(result.get("layers"), list) and isinstance(result.get("messages"), list)
    # Tools make no host requests (RustGIS refuses them); logs and progress are fine.
    assert calls == []


def test_unknown_ids_fail():
    with pytest.raises(PluginCallError):
        call_plugin({"kind": "command", "id": "no-such-command"})
