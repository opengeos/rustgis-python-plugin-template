"""My Plugin: commands on the Plugins tab.

RustGIS puts the commands declared in plugin.json in a group named after the plugin on the
Plugins tab, in command search, and on the command line (`plugin:<id>/<command>`).

- `layer-report` reads the map (`host.layers`) and shows a summary (`host.notify`).
- `zoom-largest` runs a RustGIS command (`layer.zoomTo`), as a ribbon button would.
- `pin-center` adds a layer (`host.add_layer`), which needs the `edit` permission.

Messages are worded in the interface language with `req.tr`, from the `i18n` table in
plugin.json.
"""

from __future__ import annotations

from rustgis_plugin import Request, geojson, host, serve


def handle(req: Request) -> dict:
    """Runs one of the plugin's commands.

    Args:
        req: The request.

    Returns:
        The command's answer.
    """
    if req.id == "layer-report":
        return layer_report(req)
    if req.id == "zoom-largest":
        return zoom_largest(req)
    if req.id == "pin-center":
        return pin_center(req)
    raise ValueError(f"My Plugin has no command '{req.id}'")


def layer_report(req: Request) -> dict:
    """Shows how many layers and features the map has."""
    n, features = count(host.layers())
    host.notify(req.tr("{n} layers with {features} features in all.", n=n, features=features))
    return {"layers": n, "features": features}


def zoom_largest(req: Request) -> dict:
    """Zooms to the vector layer with the most features."""
    name = largest(host.layers())
    if name is None:
        raise ValueError(req.tr("The map has no feature layers."))
    host.run("layer.zoomTo", {"layer": name})
    host.notify(req.tr("Zoomed to {name}.", name=name))
    return {"layer": name}


def pin_center(req: Request) -> dict:
    """Adds a point at the centre of the map to a new layer."""
    lon, lat = host.view()["center"]
    pins = geojson.collection([geojson.feature(geojson.point(lon, lat), {"lon": lon, "lat": lat})])
    return host.add_layer(req.params.get("name") or "Pins", pins)


def count(layers: list[dict]) -> tuple[int, int]:
    """The number of layers in `host.layers`'s answer, and of their features."""
    return len(layers), sum(layer.get("features") or 0 for layer in layers)


def largest(layers: list[dict]) -> str | None:
    """The name of the vector layer with the most features."""
    vector = [layer for layer in layers if not layer.get("raster")]
    return max(vector, key=lambda layer: layer.get("features") or 0)["name"] if vector else None


if __name__ == "__main__":
    serve(handle)
