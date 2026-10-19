"""My Plugin: a panel beside the map.

`panel` in plugin.json declares a pane of widgets bound to the plugin's commands. Its button
comes first in the plugin's group on the Plugins tab. RustGIS keeps the widgets' values (the
program runs once per call and keeps nothing) and sends them with every request, as
`req.panel`; any command can answer the panel's new state with `Panel(...).answer(...)`.

- `panel-state` runs when the panel opens and when *Vector layers only* changes: it reads the
  layers and fills the slider with their names.
- `show-layer` runs when the slider is let go or stepped. RustGIS keeps a slider's value within
  its ends, so plugin.json declares wide ones (0 to 999) for a call made before the panel's
  state has set them to the number of layers.
- `zoom-to` and `toggle-visibility` are the buttons. They act on the slider's layer, so they
  work from the ribbon, scripts and `rustgis-cli` too (which have no panes):
  `plugin:my-plugin/zoom-to={"panel": {"layer": 1}}`.

Panels need a RustGIS newer than 0.3.0; older ones ignore `panel`, and the commands still
appear on the Plugins tab.
"""

from __future__ import annotations

from rustgis_plugin import Panel, Request, host, serve


def handle(req: Request) -> dict:
    """Runs one of the panel's commands and answers the panel's new state.

    Args:
        req: The request.

    Returns:
        The answer, with the panel's state.
    """
    layers = map_layers(req)
    # The slider's layer: kept within the list, which may have changed since it was set.
    at = max(0, min(int(req.panel.get("layer") or 0), len(layers) - 1))
    if req.id in ("zoom-to", "toggle-visibility"):
        if not layers:
            raise ValueError(req.tr("The map has no layers."))
        command = "layer.zoomTo" if req.id == "zoom-to" else "layer.visibility"
        host.run(command, {"layer": layers[at]["name"]})
    elif req.id not in ("panel-state", "show-layer"):
        raise ValueError(f"My Plugin has no command '{req.id}'")
    # Read again: the command may have changed a layer (its visibility).
    layers = map_layers(req)
    return panel(req, layers, at).answer({"layer": layers[at]["name"] if layers else None})


def map_layers(req: Request) -> list[dict]:
    """The map's layers, or only its vector layers when *Vector layers only* is ticked."""
    layers = host.layers()
    return [layer for layer in layers if not layer.get("raster")] if req.panel.get("vector-only") else layers


def panel(req: Request, layers: list[dict], at: int) -> Panel:
    """The panel's state for the layer at `at`: the slider's names, the layer's summary and fields."""
    if not layers:
        none = req.tr("The map has no layers.")
        p = Panel().value("layer", 0).slider("layer", 0, 0, [none]).text("summary", none).text("fields", "")
        return p.enabled("zoom-to", False).enabled("toggle-visibility", False)
    layer = layers[at]
    visible = req.tr("visible" if layer.get("visible", True) else "hidden")
    geometry = "raster" if layer.get("raster") else layer.get("geometry") or "table"
    summary = req.tr("{features} features, {geometry}, {visible}", features=layer.get("features") or 0, geometry=geometry, visible=visible)
    names = [layer.get("name", "?") for layer in layers]
    return (
        Panel()
        .value("layer", at)
        .slider("layer", 0, len(names) - 1, names)
        .text("summary", f"{names[at]}\n{summary}")
        .text("fields", fields(layer))
        .enabled("zoom-to", True)
        .enabled("toggle-visibility", True)
    )


def fields(layer: dict) -> str:
    """A layer's fields, one `name (type)` per line."""
    return "\n".join(f"{f.get('name', '?')} ({f.get('type', '?')})" for f in layer.get("fields") or [])


if __name__ == "__main__":
    serve(handle)
