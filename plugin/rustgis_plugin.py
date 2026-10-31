"""A small SDK for RustGIS process plugins in Python: the protocol, so a plugin is a function.

RustGIS starts the plugin's program once per command or tool call. It writes the request on
standard input; the program sends host requests and log lines, then its result, one JSON
object per line on standard output (RustGIS's docs/plugins.md, "Process plugins"). This module
does that. Keep it beside main.py: it needs nothing but the standard library.

    from rustgis_plugin import Request, host, serve

    def handle(req: Request):
        if req.id == "hello":
            n = len(host.layers())
            host.notify(f"Hello! The map has {n} layers.")
            return {"layers": n}
        raise ValueError(f"unknown command '{req.id}'")

    serve(handle)

What `handle` returns is the result; an exception it raises is reported as the call's error.
While it runs, `print` writes to standard error (RustGIS logs it), so a library that prints
can't garble the protocol.
"""

from __future__ import annotations

import base64
import json
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["ABI", "Node", "Panel", "PluginError", "Request", "ToolOutput", "geojson", "host", "serve"]

#: The plugin ABI this SDK speaks. plugin.json's `abi`, when given, must match it.
ABI = 1

#: plugin.json beside this module, for its translations.
MANIFEST = Path(__file__).resolve().parent / "plugin.json"


class PluginError(Exception):
    """An error RustGIS answered to a host request."""


class _Transport:
    """The lines to and from RustGIS: standard input and the real standard output."""

    def __init__(self) -> None:
        self.input = sys.stdin
        self.output = sys.stdout

    def send(self, message: dict) -> None:
        """Writes one protocol line.

        Args:
            message: The JSON object to send.
        """
        self.output.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.output.flush()

    def call(self, op: str, params: dict) -> Any:
        """Sends a host request and waits for RustGIS's answer.

        Args:
            op: The request (`host.layers`, a command id...).
            params: Its parameters.

        Returns:
            The answer's value.

        Raises:
            PluginError: RustGIS answered an error.
        """
        self.send({"call": {"op": op, "params": params}})
        line = self.input.readline()
        if not line:
            raise PluginError("RustGIS closed the connection")
        reply = json.loads(line)
        if "error" in reply:
            raise PluginError(str(reply["error"]))
        return reply.get("ok")


class _Host:
    """Requests to RustGIS. Commands can make them; tools can only log and report progress."""

    def __init__(self) -> None:
        self.transport: Any = _Transport()

    def call(self, op: str, params: dict | None = None) -> Any:
        """Sends a request to RustGIS: a `host.*` request or a command id, with its parameters.

        Args:
            op: The request.
            params: Its parameters.

        Returns:
            RustGIS's answer.
        """
        return self.transport.call(op, params or {})

    def run(self, command: str, params: dict | None = None) -> Any:
        """Runs a RustGIS command (`layer.zoomTo`, `map.goToXY`...), within the plugin's permissions.

        Args:
            command: The command id (`rustgis-cli commands` lists them).
            params: Its parameters.

        Returns:
            What the command answers.
        """
        return self.call(command, params)

    def layers(self) -> list[dict]:
        """The map's layers.

        Returns:
            `[{"id", "name", "raster", "visible", "geometry", "features", "selected", "active", "fields"}]`.
        """
        return self.call("host.layers") or []

    def features(self, layer: str, selected: bool = False, limit: int | None = None) -> dict:
        """A layer's features as a GeoJSON FeatureCollection; each feature has its `row`.

        Args:
            layer: The layer's name.
            selected: Only the selected features.
            limit: At most this many features.

        Returns:
            The FeatureCollection.
        """
        params: dict[str, Any] = {"layer": layer, "selected": selected}
        if limit is not None:
            params["limit"] = limit
        return self.call("host.features", params)

    def view(self) -> dict:
        """The map's view.

        Returns:
            `{"center": [lon, lat], "scale", "projection"}`.
        """
        return self.call("host.view")

    def notify(self, text: str, error: bool = False) -> None:
        """Shows a message in the status bar.

        Args:
            text: The message.
            error: Show it as an error.
        """
        self.call("host.notify", {"text": text, "error": error})

    def add_layer(self, name: str, feature_collection: dict) -> Any:
        """Adds a layer from a GeoJSON FeatureCollection (needs the `edit` permission).

        Args:
            name: The layer's name.
            feature_collection: Its features.

        Returns:
            RustGIS's answer.
        """
        return self.call("host.addLayer", {"name": name, "geojson": feature_collection})

    def fetch(self, url: str) -> dict:
        """Reads a small document from the web through RustGIS (needs the `network` permission).

        A process plugin can also use the network itself, but going through RustGIS keeps the
        request within what the plugin declared.

        Args:
            url: An http:// or https:// address.

        Returns:
            `{"url", "text", "json"?}`.
        """
        return self.call("host.fetch", {"url": url})

    def log(self, text: str) -> None:
        """A line for RustGIS's log (and a tool's run messages).

        Args:
            text: The line.
        """
        self.transport.send({"log": text})

    def progress(self, text: str) -> None:
        """What a tool is doing now, shown while it runs and not kept.

        Args:
            text: The step.
        """
        self.transport.send({"progress": text})


#: Requests to RustGIS.
host = _Host()


class Request:
    """A request from RustGIS: a command or a tool to run."""

    def __init__(self, raw: dict) -> None:
        #: "command" or "tool".
        self.kind: str = raw.get("kind", "command")
        #: The command or tool id, as declared in plugin.json.
        self.id: str = raw.get("id", "")
        #: A command's parameters, or a tool's form values (defaults filled in).
        self.params: dict = raw.get("params") or {}
        #: For tools: each layer parameter's features as a FeatureCollection, by layer name.
        self.layers: dict = raw.get("layers") or {}
        #: For tools: each `file` parameter's file, `{"name", "data"}` in base64.
        self.files: dict = raw.get("files") or {}
        #: The interface language's code (`en`, `de`, `zh`...).
        self.lang: str = raw.get("lang") or "en"
        panel = raw.get("panel") or {}
        #: For a plugin with a panel: its widgets' values, by widget id.
        self.panel: dict = panel.get("values") or {}
        #: The panel widgets this call set (the one the user just moved).
        self.panel_changed: list[str] = panel.get("changed") or []

    def features(self, param: str) -> list[dict]:
        """The features of the layer a tool parameter names.

        Args:
            param: The parameter's name.

        Returns:
            The features (only the selected ones when the layer has a selection).
        """
        name = self.params.get(param)
        if not name:
            raise ValueError(f"'{param}' is required")
        if name not in self.layers:
            raise ValueError(f"no layer named '{name}'")
        return self.layers[name].get("features") or []

    def file(self, param: str) -> tuple[str, bytes]:
        """The file a tool's `file` parameter names (needs the `files` permission).

        On the desktop the parameter is also the file's path, which a process plugin can open
        itself; the contents here work everywhere.

        Args:
            param: The parameter's name.

        Returns:
            The file's name and contents.
        """
        f = self.files.get(param)
        if not f:
            raise ValueError(f"'{param}' is required")
        return f.get("name", "file"), base64.b64decode(f.get("data", ""))

    def tr(self, text: str, **args: Any) -> str:
        """`text` in the interface language, from plugin.json's `i18n`, with `{name}`s filled.

        Args:
            text: The English string, exactly as in the `i18n` tables.
            **args: Values for its `{placeholders}`.

        Returns:
            The translation, or `text` when there is none.
        """
        out = _translate(_i18n(), self.lang, text) or text
        for k, v in args.items():
            out = out.replace("{" + k + "}", str(v))
        return out

    def changed(self, widget: str) -> bool:
        """Whether this call set the panel widget `widget`.

        Args:
            widget: The widget's id.

        Returns:
            True when the user just moved it (or a script set it).
        """
        return widget in self.panel_changed


_I18N: dict | None = None


def _i18n() -> dict:
    """plugin.json's `i18n` table, read once."""
    global _I18N
    if _I18N is None:
        try:
            _I18N = json.loads(MANIFEST.read_text(encoding="utf-8")).get("i18n") or {}
        except (OSError, ValueError):
            _I18N = {}
    return _I18N


def _translate(i18n: dict, lang: str, text: str) -> str | None:
    """`text` from `i18n`: the exact code, then its language, then any region of it."""

    def base(code: str) -> str:
        return code.replace("_", "-").split("-")[0].lower()

    for want in (lambda k: k.lower() == lang.lower(), lambda k: k.lower() == base(lang), lambda k: base(k) == base(lang)):
        for code, table in i18n.items():
            if want(code) and isinstance(table, dict) and table.get(text):
                return table[text]
    return None


class ToolOutput:
    """What a tool returns: new layers and tables, or a selection, and messages."""

    def __init__(self) -> None:
        self._layers: list[dict] = []
        self._tables: list[dict] = []
        self._selection: dict | None = None
        self._messages: list[str] = []

    def layer(self, name: str, feature_collection: dict) -> ToolOutput:
        """Adds a layer.

        Args:
            name: Its name.
            feature_collection: Its features, as GeoJSON.

        Returns:
            This output.
        """
        self._layers.append({"name": name, "geojson": feature_collection})
        return self

    def table(self, name: str, feature_collection: dict) -> ToolOutput:
        """Adds a standalone table (features without geometry).

        Args:
            name: Its name.
            feature_collection: Its rows, as GeoJSON features.

        Returns:
            This output.
        """
        self._tables.append({"name": name, "geojson": feature_collection})
        return self

    def select(self, layer: str, rows: list[int]) -> ToolOutput:
        """Selects `rows` (feature indexes) of `layer` instead of adding layers.

        Args:
            layer: The layer's name.
            rows: The rows to select.

        Returns:
            This output.
        """
        self._selection = {"layer": layer, "rows": list(rows)}
        return self

    def message(self, text: str) -> ToolOutput:
        """Adds a line to the run's messages.

        Args:
            text: The line.

        Returns:
            This output.
        """
        self._messages.append(text)
        return self

    def to_dict(self) -> dict:
        """The tool's result, as RustGIS reads it.

        Returns:
            `{"layers", "tables", "messages", "selection"?}`.
        """
        out: dict[str, Any] = {"layers": self._layers, "tables": self._tables, "messages": self._messages}
        if self._selection is not None:
            out["selection"] = self._selection
        return out


@dataclass
class Node:
    """A node of a panel tree: a theme, a dataset...

    Its id is the tree's value when it is chosen:

        env = Node("env", "Environment", count=2, children=[Node("parks", "Parks"), Node("rivers", "Rivers")])
        return Panel().nodes("catalogue", [env, Node("roads", "Roads")]).answer()
    """

    #: What `req.panel.get(tree)` gives when this node is chosen.
    id: str
    #: The text the tree shows.
    label: str
    #: A number shown beside the label (the datasets in a theme, say); None shows none.
    count: int | None = None
    #: The nodes under this one.
    children: list[Node] = field(default_factory=list)

    def to_dict(self) -> dict:
        """The node, as RustGIS reads it: `count` and `children` only when it has them.

        Returns:
            `{"id", "label", "count"?, "children"?}`.
        """
        out: dict[str, Any] = {"id": self.id, "label": self.label}
        if self.count is not None:
            out["count"] = self.count
        if self.children:
            out["children"] = [c.to_dict() for c in self.children]
        return out


class Panel:
    """A panel's new state, which any command of a plugin with a panel can answer.

    What it leaves out stays as it was:

        return Panel().value("year", 2020).text("summary", "3 layers").answer({"year": 2020})
    """

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.items: dict[str, dict] = {}

    def value(self, widget: str, value: bool | int | str | None) -> Panel:
        """Sets a checkbox (`True`/`False`), a slider (a whole number) or a tree (a node's id, or
        `None` for no node chosen).

        Args:
            widget: The widget's id.
            value: Its value.

        Returns:
            This state.
        """
        self.values[widget] = value
        return self

    def text(self, widget: str, text: str) -> Panel:
        """Sets the text a `text` widget shows.

        Args:
            widget: The widget's id.
            text: The text.

        Returns:
            This state.
        """
        return self._item(widget, text=text)

    def label(self, widget: str, label: str | None) -> Panel:
        """Sets a widget's label; None brings back the declared one.

        Args:
            widget: The widget's id.
            label: The label.

        Returns:
            This state.
        """
        return self._item(widget, label=label)

    def enabled(self, widget: str, enabled: bool) -> Panel:
        """Turns a widget on or off.

        Args:
            widget: The widget's id.
            enabled: On or off.

        Returns:
            This state.
        """
        return self._item(widget, enabled=enabled)

    def visible(self, widget: str, visible: bool) -> Panel:
        """Shows or hides a widget.

        Args:
            widget: The widget's id.
            visible: Shown or hidden.

        Returns:
            This state.
        """
        return self._item(widget, visible=visible)

    def slider(self, widget: str, lo: int, hi: int, labels: list[str] | None = None) -> Panel:
        """Sets a slider's ends and, optionally, a label for each value from `lo`.

        Args:
            widget: The slider's id.
            lo: Its lowest value.
            hi: Its highest value.
            labels: One label per value.

        Returns:
            This state.
        """
        fields: dict[str, Any] = {"min": lo, "max": hi}
        if labels:
            fields["labels"] = labels
        return self._item(widget, **fields)

    def nodes(self, widget: str, nodes: Iterable[Node]) -> Panel:
        """Gives a tree its nodes, replacing the ones it had. RustGIS keeps at most 5,000 nodes, 8
        levels deep, and leaves out a node without an id, or whose id is taken already (with its
        children).

        Args:
            widget: The tree's id.
            nodes: Its top nodes, with their children.

        Returns:
            This state.
        """
        return self._item(widget, nodes=[n.to_dict() for n in nodes])

    def _item(self, widget: str, **fields: Any) -> Panel:
        self.items.setdefault(widget, {}).update(fields)
        return self

    def to_dict(self) -> dict:
        """The state, as RustGIS reads it.

        Returns:
            `{"values", "items"}`.
        """
        return {"values": self.values, "items": self.items}

    def answer(self, answer: dict | None = None) -> dict:
        """A command's answer with this state as its `panel`.

        Args:
            answer: The rest of the answer.

        Returns:
            `answer` with `panel` added.
        """
        return {**(answer or {}), "panel": self.to_dict()}


class geojson:  # noqa: N801 - used like a module: geojson.point(...)
    """Helpers for building GeoJSON."""

    @staticmethod
    def collection(features: list[dict]) -> dict:
        """A FeatureCollection of `features`."""
        return {"type": "FeatureCollection", "features": features}

    @staticmethod
    def feature(geometry: dict | None, properties: dict | None = None) -> dict:
        """A Feature."""
        return {"type": "Feature", "geometry": geometry, "properties": properties or {}}

    @staticmethod
    def point(x: float, y: float) -> dict:
        """A Point."""
        return {"type": "Point", "coordinates": [x, y]}

    @staticmethod
    def polygon(ring: list[list[float]]) -> dict:
        """A Polygon from one ring, closed if it isn't."""
        ring = [list(p) for p in ring]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        return {"type": "Polygon", "coordinates": [ring]}

    @staticmethod
    def positions(geometry: dict | None) -> list[list[float]]:
        """Every position of a geometry, of any type."""
        out: list[list[float]] = []

        def walk(c: Any) -> None:
            if isinstance(c, list) and c and isinstance(c[0], (int, float)):
                out.append(c[:2])
            elif isinstance(c, list):
                for x in c:
                    walk(x)

        if geometry:
            if geometry.get("type") == "GeometryCollection":
                for g in geometry.get("geometries") or []:
                    out += geojson.positions(g)
            else:
                walk(geometry.get("coordinates"))
        return out


def _result(value: Any) -> Any:
    """`value` as JSON RustGIS reads: ToolOutput and Panel become dicts."""
    if isinstance(value, (ToolOutput, Panel)):
        return value.to_dict()
    return value


def serve(handler: Callable[[Request], Any]) -> None:
    """Answers RustGIS's request with `handler`: the plugin's entry point.

    Args:
        handler: Takes the Request; returns the result (a dict, a ToolOutput...) or raises.
    """
    transport = host.transport
    line = transport.input.readline()
    try:
        raw = json.loads(line)
    except ValueError as e:
        transport.send({"error": f"unreadable request: {e}"})
        return
    # Prints go to standard error while the handler runs: RustGIS logs them.
    stdout, sys.stdout = sys.stdout, sys.stderr
    try:
        message = {"ok": _result(handler(Request(raw)))}
    except Exception as e:  # noqa: BLE001 - every failure is the call's error
        message = {"error": str(e) or type(e).__name__}
    finally:
        sys.stdout = stdout
    transport.send(message)
