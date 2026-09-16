# Bernardyn local MCP server

`bernardyn-mcp` is a local stdio server for creating and inspecting portable
Bernardyn figures. It is a thin adapter over the public headless recipe API;
it does not fit data, alter source files, execute code, or expose raw HDF5
writing.

## Install and configure

Install the optional MCP dependency:

```sh
pip install 'bernardyn[mcp]'
```

Configure an MCP-capable local agent to run the installed executable. Use an
absolute command path if the client does not inherit your shell environment:

```json
{
  "mcpServers": {
    "bernardyn": {
      "command": "/path/to/environment/bin/bernardyn-mcp",
      "env": {
        "BERNARDYN_DATA_ROOT": "/path/to/authorised-inputs",
        "BERNARDYN_OUTPUT_ROOT": "/path/to/authorised-outputs"
      }
    }
  }
}
```

`BERNARDYN_DATA_ROOT` is optional. When set, source/package reads are limited
to it (and to the output root, so created packages can be inspected or
exported). `BERNARDYN_OUTPUT_ROOT` is optional; without it, artifacts are
written under the local temporary `bernardyn-mcp` cache. MCP output names are
simple filenames only, so an agent cannot escape the output root with a path
or traversal sequence.

The stdio protocol uses stdout exclusively. Diagnostic logging is written to
stderr.

## Five-tool surface

The server deliberately exposes only five tools in three workflow groups. It
does not create one tool per scientific view or pyIrena result type.

| Group | Tool | Use |
|---|---|---|
| Discovery | `bernardyn_inspect_data` | Inspect one file's scattering selections, saved results, and warnings. |
| Discovery | `bernardyn_list_plot_recipes` | List stable recipe IDs and their scientific purpose. |
| Create | `bernardyn_create_plot` | Create one native package and PNG/JPEG/SVG preview through a recipe. |
| Package | `bernardyn_describe_package` | Inspect graphs, curve semantics, recipe identity, and warnings without returning arrays. |
| Package | `bernardyn_export_plot` | Re-render one stored 2-D graph to an authorised output artifact. |

Start with `bernardyn_inspect_data`, then choose a recipe from
`bernardyn_list_plot_recipes`. Use `bernardyn_create_plot` for all creation:
it accepts scattering `input_paths` for scattering recipes, or `result_path`
for saved-result recipes. It returns package and preview paths plus loaded,
plotted, and masked point counts.

`output_name` is a filename stem, not a path. Existing generated artifacts are
rejected unless `overwrite: true` is explicit. This avoids accidental output
replacement during retries. Large canonical arrays remain in the package;
tool responses contain only compact metadata and diagnostics.

## Example workflow

1. Call `bernardyn_inspect_data` for a saved `.h5` file.
2. Call `bernardyn_create_plot` with `recipe_id:
   "unified_fit_residuals"`, its `result_path`, and `output_name:
   "sample-residuals"`.
3. Review the returned preview path and point-count diagnostics.
4. Call `bernardyn_describe_package` with the returned package path to inspect
   the recorded generic residual semantics.
5. If needed, call `bernardyn_export_plot` with that graph ID and an SVG
   output name.

The first server process is intentionally local and stateless: every create
call has an isolated workspace. Live desktop-GUI control, remote transport,
and fitting remain outside this server.
