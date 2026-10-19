"""My Plugin: a ribbon tab of its own.

`tab` in plugin.json lays the plugin's commands and tools out on a tab at the end of the tab
strip, in groups, with a dropdown menu. An item is a command id, `tool:<id>` (which opens that
tool in the Tools pane) or a `menu` of them.

- `go-*` and `zoom-world` move the map with RustGIS's own commands (`map.goToXY`,
  `map.zoomWorld`). They change only the view, so the plugin needs no permissions.
- `layer-report` reads the map and shows a summary in the status bar.
- `bounding-boxes` is a geoprocessing tool: it gets its input layer as GeoJSON and returns a
  new layer, which RustGIS adds with undo.
"""

from __future__ import annotations

from rustgis_plugin import Request, ToolOutput, geojson, host, serve

#: Where each `go-*` command goes: (longitude, latitude, scale).
PLACES = {
    "go-africa": (20.0, 2.0, 40_000_000),
    "go-americas": (-80.0, 10.0, 70_000_000),
    "go-asia": (95.0, 35.0, 50_000_000),
    "go-europe": (15.0, 52.0, 20_000_000),
}


def handle(req: Request) -> dict | ToolOutput:
    """Runs one of the plugin's commands or tools.

    Args:
        req: The request.

    Returns:
        The answer.
    """
    if req.kind == "tool" and req.id == "bounding-boxes":
        return bounding_boxes(req)
    if req.id in PLACES:
        lon, lat, scale = PLACES[req.id]
        return host.run("map.goToXY", {"lon": lon, "lat": lat, "scale": scale})
    if req.id == "zoom-world":
        return host.run("map.zoomWorld")
    if req.id == "layer-report":
        layers = host.layers()
        features = sum(layer.get("features") or 0 for layer in layers)
        host.notify(req.tr("{n} layers with {features} features in all.", n=len(layers), features=features))
        return {"layers": len(layers), "features": features}
    raise ValueError(f"My Plugin has no '{req.id}'")


def bounding_boxes(req: Request) -> ToolOutput:
    """Draws the bounding box of each feature, or of the whole layer."""
    features = req.features("input")
    if req.params.get("whole"):
        points = [p for f in features for p in geojson.positions(f.get("geometry"))]
        boxes = [box_feature(b, {"features": len(features)})] if (b := bbox(points)) else []
    else:
        boxes = [box_feature(b, f.get("properties")) for f in features if (b := bbox(geojson.positions(f.get("geometry"))))]
    name = req.params.get("input") or "Input"
    return ToolOutput().layer(f"{name} boxes", geojson.collection(boxes)).message(f"{len(boxes)} boxes")


def bbox(points: list[list[float]]) -> tuple[float, float, float, float] | None:
    """The bounding box of `points`: (min x, min y, max x, max y)."""
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def box_feature(b: tuple[float, float, float, float], properties: dict | None) -> dict:
    """A polygon feature for a bounding box."""
    x0, y0, x1, y1 = b
    return geojson.feature(geojson.polygon([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]), properties)


if __name__ == "__main__":
    serve(handle)
