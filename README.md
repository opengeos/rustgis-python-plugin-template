# RustGIS Python Plugin Template

A template for [RustGIS](https://github.com/opengeos/RustGIS) plugins written in Python. A
Python plugin is a *process plugin*: a program that RustGIS starts for each command or tool
call, speaking JSON lines over its standard input and output. RustGIS gives it a Python
environment of its own, with the packages in `requirements.txt` (made with
[uv](https://github.com/astral-sh/uv) when the plugin is installed). So a plugin can use
numpy, Shapely, xarray, GDAL bindings and the rest without its users installing anything.

Click **Use this template** on GitHub (or fork this repository), pick a starter, and the
workflows here test and release your plugin, ready to submit to the
[plugin registry](https://plugins.rustgis.app).

> [!WARNING]
> **Python plugins are not sandboxed.** A process plugin runs as a program on the user's
> computer and can do anything they can. RustGIS says so before it installs one, and the
> registry reviews them more strictly. Process plugins run in the desktop app and
> `rustgis-cli`, not in the web app. For a sandboxed plugin that runs everywhere, write it in
> Rust with [rustgis-plugin-template](https://github.com/opengeos/rustgis-plugin-template).

## Starters

Each starter in [`starters/`](starters) is a complete plugin that shows one way a plugin
appears in RustGIS:

| Starter | Where it appears | What it shows |
|---|---|---|
| [`commands`](starters/commands) (the default) | buttons in a group named after the plugin on the **Plugins** tab | reading the map, running RustGIS commands, adding a layer, translated messages |
| [`tab`](starters/tab) | a ribbon tab of its own, with groups, a dropdown menu and a tool button | `tab` in `plugin.json`, moving the map, a tool opened from the ribbon |
| [`panel`](starters/panel) | a pane beside the map, opened from the **Plugins** tab | `panel` in `plugin.json`: a slider, a checkbox, texts and buttons bound to commands, and the state the plugin answers (a `tree` of nodes it gives too) |
| [`tools`](starters/tools) | geoprocessing tools in the **Tools** pane, under **Plugins ›** | tool parameters (layer, field, choice, number, bool), new layers and a selection, made with Shapely from `requirements.txt` |

The sections are independent: one plugin can have commands, tools, a tab and a panel. Start
from one starter and copy what you need from the others.

Panels need a RustGIS newer than 0.3.0. Older versions ignore `panel`, and the panel starter's
commands still appear on the Plugins tab. A panel `tree` (nodes the plugin gives with
`Panel().nodes(...)` and `Node`, the chosen one's id in `req.panel`) needs a RustGIS newer than
0.4.0, which refuses a manifest with one.

## Quick start

You need Python 3.11 or later, and RustGIS 0.3.0 or later.

```sh
# Pick a starter (commands, tab, panel or tools) and name your plugin.
python scripts/setup.py --starter tools --id my-plugin --name "My Plugin" --author "Your Name"
```

Everything RustGIS runs is in [`plugin/`](plugin):

| File | What |
|---|---|
| `plugin.json` | the manifest: id, version, permissions, commands, tools, tab, panel, translations, and `runtime`, `python` and `run` |
| `main.py` | the plugin |
| `rustgis_plugin.py` | the SDK: the protocol, `host` requests, `Request`, `ToolOutput`, `Panel`, `Node` (standard library only) |
| `requirements.txt` | the packages the plugin needs |

Put any other modules or data files the plugin needs in `plugin/` as well; the package holds
the whole folder.

`setup.py` copies the starter's `plugin.json`, `main.py` and `requirements.txt` into
`plugin/`. It also sets the plugin's id, name, author and homepage. It takes the homepage, and
by default the id and author, from your repository's GitHub address. Run it again to switch
starters, but note that it overwrites those three files. Once you've picked one, you can
delete `starters/` and `scripts/setup.py`.

## Develop

- **Try it in RustGIS:** open **Plugins › Plugin Manager › Settings › Add Plugin Folder…** and
  pick `plugin/`. RustGIS runs it where it is, and makes its Python environment. A change to
  `main.py` applies from the next call. Add the folder again (or restart RustGIS) after you
  change `plugin.json`, and use **Prepare** in the Plugin Manager after you change
  `requirements.txt`.
- **Try it on the command line:**

  ```sh
  rustgis-cli plugins install ./plugin && rustgis-cli plugins prepare my-plugin
  rustgis-cli run --sample --cmd 'plugin:my-plugin/layer-report'
  rustgis-cli run --sample \
    --cmd 'gp.run={"tool": "plugin:my-plugin/convex-hulls", "params": {"input": "Countries"}}' \
    --cmd 'share.exportMap={"path": "map.png"}'
  ```

- **Tests:** `pip install -r plugin/requirements.txt pytest`, then `pytest`.
  [`tests/fake_rustgis.py`](tests/fake_rustgis.py) runs `plugin/main.py` as RustGIS does and
  answers its host requests from a small sample map. `tests/test_plugin.py` runs every command
  and tool. Add tests of your own there.
- **Run it as CI does:** `python scripts/package.py`, then `python scripts/smoke.py`. They
  install the package in `rustgis-cli`, make its environment, and run it on the World Atlas
  sample. Every tool runs with its defaults, and so does every command that needs no
  parameters. `--strict` also fails when a command fails.
- **Lint:** `pre-commit run --all-files` (ruff).

The plugin is a function that answers requests:

```python
from rustgis_plugin import Request, host, serve


def handle(req: Request):
    if req.id == "layer-report":
        n = len(host.layers())
        host.notify(req.tr("{n} layers", n=n))
        return {"layers": n}
    raise ValueError(f"unknown command '{req.id}'")


if __name__ == "__main__":
    serve(handle)
```

`host` sends requests to RustGIS: `host.layers()`, `host.features(layer)`, `host.view()`,
`host.notify(text)`, `host.add_layer(name, geojson)`, `host.fetch(url)`, and
`host.run(command, params)` for any RustGIS command (`rustgis-cli commands` lists them).
Permissions (`edit`, `files`, `network`) decide which of these RustGIS answers. They don't
limit what the program itself can do. Tools get their layers as GeoJSON in `req.features(...)`
and return a `ToolOutput`. They make no host requests, but they can `host.log` and
`host.progress`. Anything the plugin prints goes to RustGIS's log, not into the protocol.

See RustGIS's [plugin documentation](https://github.com/opengeos/RustGIS/blob/main/docs/plugins.md)
(*Process plugins*, *A panel*, *A tab of its own*, *Translations*) and
[Write a plugin](https://plugins.rustgis.app/develop/) for the manifest.

## Release

1. Bump `version` in `plugin/plugin.json`. Packages never change once published, so every
   release needs a new version.
2. Commit, then push a tag that matches the version:

   ```sh
   git tag v0.1.0
   git push origin v0.1.0
   ```

The [Release](.github/workflows/release.yml) workflow checks the plugin, runs it in the latest
RustGIS, and publishes a GitHub release with two files:

- `<id>-<version>.rgplugin`, the package.
- `<id>.json`, the registry entry, with the package's address and SHA-256.

The release notes repeat the entry. Anyone can install the package from the release, through
**Plugin Manager › Settings › Install From File…** or with
`rustgis-cli plugins install <file>`.

A tag that doesn't match `plugin.json`'s version fails the workflow. CI tests against the latest
RustGIS release; set the `RUSTGIS_VERSION` repository variable (to `v0.3.0`, say) to test
against another one.

## Submit to the plugin registry

The [registry](https://plugins.rustgis.app) is curated: a maintainer reviews each plugin before
it is listed, and a plugin that isn't sandboxed gets a close read of its code. Keep `main.py`
readable, ask only for the permissions you use, and list your requirements. To submit your
plugin, open a pull request on
[opengeos/rustgis-plugins](https://github.com/opengeos/rustgis-plugins) that adds
`registry/<id>.json`:

1. Take `<id>.json` from your release (or `dist/<id>.json`). Set its `categories` to one to four
   of: Analysis, Basemaps, Cartography, Data, Editing, Example, Hydrology, Imagery, Raster,
   Sampling, Terrain, Utilities, Vector, Visualization.

   ```json
   {
     "id": "my-plugin",
     "source": {
       "url": "https://github.com/you/my-plugin/releases/download/v0.1.0/my-plugin-0.1.0.rgplugin",
       "sha256": "..."
     },
     "categories": ["Analysis"]
   }
   ```

2. Add it as `registry/<id>.json` and open the pull request, on the web or with `gh`:

   ```sh
   gh repo fork opengeos/rustgis-plugins --clone && cd rustgis-plugins
   git switch -c add-my-plugin
   cp ../my-plugin/dist/my-plugin.json registry/   # then edit its categories
   git add registry/my-plugin.json && git commit -m "Add My Plugin to the registry"
   git push -u origin add-my-plugin && gh pr create --fill
   ```

The registry's CI downloads the package, checks its SHA-256, and validates it. The listing's
name, description, version and permissions come from your `plugin.json`. The listing marks
your plugin **Not sandboxed**. Once the PR is merged, the package is served from
`packages.rustgis.app`, and RustGIS users on the desktop can install it from
**Plugins › Plugin Manager › Browse**.

**Updating:** release a new version, then open a pull request that updates `source` in
`registry/<id>.json` to the new release's `url` and `sha256`. RustGIS shows an **Update**
button to everyone with an older version.

See [Publish a plugin](https://plugins.rustgis.app/registry/) for what the review looks at.

## Layout

| Path | What |
|---|---|
| `plugin/` | the plugin: everything in it is packaged |
| `starters/` | the four starters |
| `tests/` | pytest tests, with a stand-in for RustGIS |
| `scripts/setup.py` | picks a starter and names the plugin |
| `scripts/package.py` | checks the plugin and packages `plugin/` into `dist/` |
| `scripts/smoke.py` | installs the package in `rustgis-cli` and runs it |
| `.github/workflows/ci.yml` | lints, tests and runs the plugin on each push and pull request |
| `.github/workflows/release.yml` | publishes a release when you push a `v*` tag |

## License

MIT for the template. Your plugin states its own license in `plugin.json`.
