"""Command-line access to the public Bernardyn plot recipes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bernardyn.api import (
    PlotRequest,
    Presentation,
    ResultInput,
    ScatteringInput,
    create_plot,
    inspect_data,
    list_recipes,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bernardyn-plot", description="Create Bernardyn plot recipes")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-recipes", help="List supported plot recipes")
    inspect = commands.add_parser("inspect", help="Inspect available scattering/results selections")
    inspect.add_argument("path", type=Path)
    create = commands.add_parser("create", help="Create a package and optional image")
    create.add_argument("--recipe", required=True, choices=[item.id for item in list_recipes()])
    create.add_argument("--input", action="append", type=Path, default=[], help="Source or result file")
    create.add_argument("--internal-path", action="append", default=[], help="Exact HDF5 scattering group")
    create.add_argument("--package", type=Path, help="Output .bernardyn.h5 package")
    create.add_argument("--image", type=Path, help="Optional PNG, JPEG, or SVG output")
    create.add_argument("--title")
    create.add_argument("--width-px", type=int)
    create.add_argument("--height-px", type=int)
    create.add_argument("--dpi", type=int)
    create.add_argument("--parameter", action="append", default=[], metavar="NAME=VALUE")
    create.add_argument("--template", type=Path)
    create.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list-recipes":
            print(json.dumps([item.__dict__ for item in list_recipes()], indent=2))
            return 0
        if args.command == "inspect":
            print(json.dumps(inspect_data(args.path), indent=2))
            return 0
        request = _request_from_args(args)
        result = create_plot(request)
        print(
            json.dumps(
                {
                    "graph_id": result.graph.id,
                    "artifacts": [item.__dict__ | {"path": str(item.path)} for item in result.artifacts],
                    "diagnostics": result.diagnostics.__dict__,
                },
                default=str,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"bernardyn-plot: {exc}", file=sys.stderr)
        return 2


def _request_from_args(args: argparse.Namespace) -> PlotRequest:
    parameters = _parameters(args.parameter)
    result_recipe = args.recipe.startswith(("unified_fit_", "size_distribution_"))
    if result_recipe:
        if len(args.input) != 1:
            raise ValueError("saved-result recipes require exactly one --input file")
        analysis = "unified_fit" if args.recipe.startswith("unified_fit_") else "size_distribution"
        result = ResultInput(args.input[0], analysis)
        inputs = ()
        parameter_rows = ()
    else:
        if len(args.internal_path) > len(args.input):
            raise ValueError("provide no more --internal-path values than --input files")
        inputs = tuple(
            ScatteringInput(path, internal_path=args.internal_path[index] if index < len(args.internal_path) else None)
            for index, path in enumerate(args.input)
        )
        result = None
        parameter_rows = tuple(parameters for _ in inputs) if parameters else ()
    return PlotRequest(
        recipe_id=args.recipe,
        inputs=inputs,
        result=result,
        series_parameters=parameter_rows,
        presentation=Presentation(
            title=args.title,
            width_px=args.width_px,
            height_px=args.height_px,
            dpi=args.dpi,
            template_path=args.template,
        ),
        package_path=args.package,
        image_path=args.image,
        overwrite=args.overwrite,
    )


def _parameters(values: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for value in values:
        name, separator, number = value.partition("=")
        if not separator or not name:
            raise ValueError(f"invalid --parameter {value!r}; use NAME=VALUE")
        try:
            result[name] = float(number)
        except ValueError as exc:
            raise ValueError(f"invalid --parameter {value!r}; VALUE must be numeric") from exc
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
