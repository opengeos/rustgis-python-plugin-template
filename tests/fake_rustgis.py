"""A stand-in for RustGIS: runs plugin/main.py as RustGIS does, and answers its requests.

    result, calls = call_plugin({"kind": "command", "id": "layer-report"})

`call_plugin` starts the program, writes the request, answers each host request from
`answers` (by op, a value or a function of the params; else from the sample map below), and
returns the plugin's result and the requests it made. An `{"error": ...}` result raises
PluginCallError.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

PLUGIN = Path(__file__).resolve().parent.parent / "plugin"
MANIFEST = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))

#: Layers like the World Atlas sample's.
LAYERS = [
    {
        "id": "1",
        "name": "Cities",
        "raster": False,
        "visible": True,
        "geometry": "Point",
        "features": 3,
        "fields": [{"name": "name", "type": "Text"}, {"name": "pop_max", "type": "Integer"}],
    },
    {
        "id": "2",
        "name": "Countries",
        "raster": False,
        "visible": True,
        "geometry": "Polygon",
        "features": 2,
        "fields": [{"name": "name", "type": "Text"}, {"name": "pop_est", "type": "Integer"}],
    },
]

#: Two countries, as a tool gets them.
COUNTRIES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 2], [0, 2], [0, 0]]]},
            "properties": {"name": "A", "pop_est": 10},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [12, 10], [11, 13], [10, 10]]]},
            "properties": {"name": "B", "pop_est": 500},
        },
    ],
}

DEFAULTS: dict[str, Any] = {
    "host.layers": LAYERS,
    "host.view": {"center": [8.5, 47.4], "scale": 50000, "projection": "EPSG:3857"},
    "host.notify": None,
    "host.addLayer": {"layer": "added"},
}


class PluginCallError(Exception):
    """The plugin answered an error."""


def call_plugin(request: dict, answers: dict[str, Any | Callable[[dict], Any]] | None = None) -> tuple[Any, list[dict]]:
    """Runs plugin/main.py on one request, as RustGIS would.

    Args:
        request: The request (`abi`, `lang` and `params` are filled in when missing).
        answers: Answers to host requests, by op: a value, or a function of the params.

    Returns:
        The plugin's result, and the host requests it made (`{"op", "params"}`).

    Raises:
        PluginCallError: The plugin answered an error.
    """
    request = {"abi": 1, "lang": "en", "params": {}, **request}
    answers = {**DEFAULTS, **(answers or {})}
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=PLUGIN, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    calls: list[dict] = []
    result: dict | None = None
    for line in proc.stdout:
        msg = json.loads(line)
        if "call" in msg:
            call = msg["call"]
            calls.append(call)
            op = call["op"]
            answer = answers.get(op, {} if "." in op else None)
            value = answer(call.get("params") or {}) if callable(answer) else answer
            proc.stdin.write(json.dumps({"ok": value}) + "\n")
            proc.stdin.flush()
        elif "ok" in msg or "error" in msg:
            result = msg
            break
    proc.stdin.close()
    proc.wait(timeout=30)
    if result is None:
        raise PluginCallError("the plugin gave no result")
    if "error" in result:
        raise PluginCallError(result["error"])
    return result["ok"], calls
