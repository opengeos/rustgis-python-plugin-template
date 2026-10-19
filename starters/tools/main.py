"""My Plugin: geoprocessing tools, with Shapely.

A plugin's `tools` appear in the Tools pane under Plugins › <toolbox>, in command search, in
`gp.run` and on the command line, with a form RustGIS builds from their `params`. A tool gets
its layer parameters' features as GeoJSON (only the selected features when a layer has a
selection) and returns new layers, tables or a selection, which RustGIS applies with undo.

A Python plugin can use any library: requirements.txt lists them, and RustGIS installs them
into the plugin's own environment. Here Shapely does the geometry.

- `convex-hulls` and `centroids` return new layers.
- `select-by-value` returns a selection, reading a `numericField`, a `choice` and a `number`.

Try them on the command line:

    rustgis-cli run --sample --cmd 'gp.run={"tool": "plugin:my-plugin/convex-hulls", "params": {"input": "Countries"}}'
"""

from __future__ import annotations

import operator

from rustgis_plugin import Request, ToolOutput, geojson, host, serve
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

#: The `op` choice's values.
COMPARE = {"greater than": operator.gt, "less than": operator.lt, "equal to": operator.eq}


def handle(req: Request) -> ToolOutput:
    """Runs one of the plugin's tools.

    Args:
        req: The request.

    Returns:
        The tool's output.
    """
    tools = {"convex-hulls": convex_hulls, "centroids": centroids, "select-by-value": select_by_value}
    if req.kind != "tool" or req.id not in tools:
        raise ValueError(f"My Plugin has no '{req.id}'")
    return tools[req.id](req)


def geometries(req: Request) -> list[tuple[object, dict]]:
    """The input layer's features as (Shapely geometry, properties), skipping empty ones."""
    out = []
    for f in req.features("input"):
        if f.get("geometry"):
            out.append((shape(f["geometry"]), f.get("properties") or {}))
    return out


def convex_hulls(req: Request) -> ToolOutput:
    """Draws the convex hull of each feature, or of the whole layer."""
    shapes = geometries(req)
    host.progress(f"{len(shapes)} features")
    if req.params.get("whole"):
        hulls = [(unary_union([g for g, _ in shapes]).convex_hull, {"features": len(shapes)})] if shapes else []
    else:
        hulls = [(g.convex_hull, p) for g, p in shapes]
    features = [geojson.feature(mapping(g), p) for g, p in hulls]
    name = f"{req.params.get('input', 'Input')} hulls"
    return ToolOutput().layer(name, geojson.collection(features)).message(req.tr("{n} hulls", n=len(features)))


def centroids(req: Request) -> ToolOutput:
    """Adds a point at each feature's centroid, or a point surely inside it."""
    inside = bool(req.params.get("inside"))
    points = [geojson.feature(mapping(g.representative_point() if inside else g.centroid), p) for g, p in geometries(req)]
    name = f"{req.params.get('input', 'Input')} centroids"
    return ToolOutput().layer(name, geojson.collection(points)).message(req.tr("{n} centroids", n=len(points)))


def select_by_value(req: Request) -> ToolOutput:
    """Selects the features whose numeric field compares with a value."""
    layer, field = req.params.get("input"), req.params.get("field")
    if not field:
        raise ValueError("'field' is required")
    compare = COMPARE.get(req.params.get("op"), operator.gt)
    value = float(req.params.get("value") or 0)
    features = req.features("input")
    # Rows are positions in what the tool got: the whole layer, or its selected features.
    rows = [i for i, f in enumerate(features) if matches((f.get("properties") or {}).get(field), compare, value)]
    message = req.tr("{n} of {total} features selected", n=len(rows), total=len(features))
    return ToolOutput().select(layer, rows).message(message)


def matches(v: object, compare, value: float) -> bool:
    """Whether the field value `v` is a number that compares with `value`."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and compare(v, value)


if __name__ == "__main__":
    serve(handle)
