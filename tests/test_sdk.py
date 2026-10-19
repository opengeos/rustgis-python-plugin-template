"""Tests of rustgis_plugin, the SDK: requests, answers and the protocol."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))

import rustgis_plugin as rp  # noqa: E402


class Lines:
    """A transport that reads canned lines and records what is sent."""

    def __init__(self, *lines: dict) -> None:
        self.input = io.StringIO("".join(json.dumps(x) + "\n" for x in lines))
        self.sent: list[dict] = []

    def send(self, message: dict) -> None:
        self.sent.append(message)

    def call(self, op: str, params: dict):
        return rp._Transport.call(self, op, params)  # type: ignore[arg-type]


def serve(handler, *lines: dict) -> list[dict]:
    """Runs `serve(handler)` on canned lines and returns what it sent."""
    t = Lines(*lines)
    rp.host.transport = t
    try:
        rp.serve(handler)
    finally:
        rp.host.transport = rp._Transport()
    return t.sent


def test_a_command_calls_the_host_and_answers():
    def handle(req: rp.Request):
        n = len(rp.host.layers())
        print("libraries may print")  # goes to standard error, not the protocol
        return {"layers": n, "id": req.id}

    sent = serve(handle, {"kind": "command", "id": "count"}, {"ok": [{"name": "A"}, {"name": "B"}]})
    assert sent == [{"call": {"op": "host.layers", "params": {}}}, {"ok": {"layers": 2, "id": "count"}}]


def test_errors_are_the_calls_error():
    def handle(req: rp.Request):
        rp.host.run("layer.zoomTo", {"layer": "X"})

    sent = serve(handle, {"kind": "command", "id": "z"}, {"error": "no layer named 'X'"})
    assert sent[-1] == {"error": "no layer named 'X'"}
    assert serve(lambda req: 1 / 0, {"kind": "command", "id": "z"})[-1] == {"error": "division by zero"}
    assert "unreadable request" in serve(lambda req: None)[-1]["error"]


def test_requests_carry_panel_values_and_files():
    req = rp.Request(
        {
            "kind": "tool",
            "id": "t",
            "params": {"input": "Countries", "model": "run.nc"},
            "layers": {"Countries": {"features": [{"properties": {}}]}},
            "files": {"model": {"name": "run.nc", "data": "Q0RGAQ=="}},
            "panel": {"values": {"year": 2020, "local": True}, "changed": ["year"]},
            "lang": "de",
        }
    )
    assert len(req.features("input")) == 1
    assert req.file("model") == ("run.nc", b"CDF\x01")
    assert req.panel == {"year": 2020, "local": True} and req.changed("year") and not req.changed("local")
    assert rp.Request({}).panel == {} and rp.Request({}).lang == "en"


def test_translations_follow_the_language():
    rp._I18N = {"de": {"Zoomed to {name}.": "Auf {name} gezoomt."}, "zh-CN": {"Hi": "你好"}}
    try:
        assert rp.Request({"lang": "de"}).tr("Zoomed to {name}.", name="Cities") == "Auf Cities gezoomt."
        assert rp.Request({"lang": "de-AT"}).tr("Zoomed to {name}.", name="X") == "Auf X gezoomt."
        assert rp.Request({"lang": "zh"}).tr("Hi") == "你好"
        assert rp.Request({"lang": "fr"}).tr("Zoomed to {name}.", name="X") == "Zoomed to X."
    finally:
        rp._I18N = None


def test_tool_output_and_panel_state():
    out = rp.ToolOutput().layer("L", rp.geojson.collection([])).select("L", [1, 2]).message("m").to_dict()
    assert out == {
        "layers": [{"name": "L", "geojson": {"type": "FeatureCollection", "features": []}}],
        "tables": [],
        "messages": ["m"],
        "selection": {"layer": "L", "rows": [1, 2]},
    }
    p = rp.Panel().value("year", 3).text("t", "x").slider("year", 0, 3, ["a", "b", "c", "d"]).enabled("b", False).label("t", None)
    assert p.answer({"year": 3}) == {
        "year": 3,
        "panel": {
            "values": {"year": 3},
            "items": {"t": {"text": "x", "label": None}, "year": {"min": 0, "max": 3, "labels": ["a", "b", "c", "d"]}, "b": {"enabled": False}},
        },
    }


def test_geojson_helpers():
    assert rp.geojson.polygon([[0, 0], [1, 0], [1, 1]])["coordinates"][0][-1] == [0, 0]
    multi = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [0, 1], [0, 0]]]]}
    assert rp.geojson.positions(multi) == [[0, 0], [1, 0], [0, 1], [0, 0]]
    assert rp.geojson.positions({"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [1, 2, 3]}]}) == [[1, 2]]
