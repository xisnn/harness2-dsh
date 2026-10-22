# Copyright 2026 harness2-dsh contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Command line interface: `harness2-dsh convert` and `harness2-dsh inspect`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import convert as convert_mod
from . import tree as harness_tree


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness2-dsh",
        description=(
            "Convert a Google Research Harness2 harness tree into a DeepSeek Harness "
            "(DSH) agent-preset bundle."
        ),
    )
    p.add_argument("--version", action="version", version=f"harness2-dsh {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("convert", help="convert a harness tree into a bundle directory")
    c.add_argument("source", type=Path, help="the Harness2 harness directory")
    c.add_argument("--out", type=Path, required=True, help="bundle directory to create")
    c.add_argument("--preset-id", default="", help="preset id (default: from --name or the dir name)")
    c.add_argument("--name", default="", help="display name shown in the preset picker")
    c.add_argument("--description", default="", help="preset description")
    c.add_argument("--order", type=int, default=50, help="roster position (default 50)")
    c.add_argument(
        "--persona-mode",
        choices=("append", "replace"),
        default="append",
        help=(
            "append: keep DSH's own system prompt and add the harness text after it; "
            "replace: make the harness text the whole system prompt"
        ),
    )
    c.add_argument(
        "--skill-path-mode",
        choices=("absolute", "dsh-home"),
        default="absolute",
        help=(
            "absolute: write the resolved skills path into the patch (works anywhere); "
            "dsh-home: emit dshHomePath(...) (only valid when the bundle is installed "
            "under $DSH_HOME/profiles/<profile>/)"
        ),
    )
    c.add_argument("--with-subagents", action="store_true", help="convert sub_agents/ into child presets")
    c.add_argument("--no-scripts", action="store_true", help="skip scripts/")
    c.add_argument("--profile", default="", help="profile name used in the generated install hint")
    c.add_argument("--json", action="store_true", help="print a machine-readable summary")

    i = sub.add_parser("inspect", help="show what a harness tree contains, without converting")
    i.add_argument("source", type=Path)
    i.add_argument("--json", action="store_true")
    return p


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        root, how = harness_tree.resolve_harness_root(args.source)
        harness = harness_tree.load(root)
    except ValueError as exc:
        print(f"harness2-dsh: {exc}", file=sys.stderr)
        return 2
    stats = harness.summary()
    if args.json:
        print(
            json.dumps(
                {
                    "root": str(harness.root),
                    "source": str(args.source),
                    "source_kind": how,
                    **stats,
                    "skills": [s.name for s in harness.skills],
                    "subagents": [s.name for s in harness.subagents],
                    "scripts": sorted(harness.scripts),
                    "plugins": sorted(harness.plugins),
                    "warnings": harness.warnings,
                },
                indent=2,
            )
        )
        return 0
    print(f"harness: {harness.root}")
    if how != "harness directory":
        print(f"  located as     : {how}")
    print(f"  always-on text : {stats['always_on_chars']:,} chars")
    print(f"  skills         : {stats['skills']}")
    for skill in harness.skills:
        print(f"    - {skill.name}: {skill.description[:70]}")
    print(f"  subagents      : {stats['subagents']}")
    for agent in harness.subagents:
        print(f"    - {agent.name}: {agent.description[:70]}")
    print(f"  scripts        : {stats['scripts']} ({', '.join(sorted(harness.scripts)) or '-'})")
    print(f"  plugins        : {stats['plugins']} ({', '.join(sorted(harness.plugins)) or '-'})")
    for warning in harness.warnings:
        print(f"  ! {warning}")
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    preset_id = args.preset_id or convert_mod.normalise_preset_id(
        args.name or args.out.name or args.source.name
    )
    opts = convert_mod.Options(
        preset_id=preset_id,
        preset_name=args.name or preset_id,
        description=args.description,
        order=args.order,
        persona_mode=args.persona_mode,
        skill_path_mode=args.skill_path_mode,
        with_subagents=args.with_subagents,
        with_scripts=not args.no_scripts,
        install_hint_profile=args.profile,
    )
    try:
        result = convert_mod.convert(args.source, args.out, opts)
    except (ValueError, OSError) as exc:
        print(f"harness2-dsh: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "bundle": str(result.out_dir),
                    "preset_id": result.preset_id,
                    "preset_row_id": result.preset_row_id,
                    "files": [str(p) for p in result.files],
                    "harness": result.harness.summary(),
                    "warnings": result.warnings,
                },
                indent=2,
            )
        )
        return 0

    stats = result.harness.summary()
    print(f"wrote bundle: {result.out_dir}")
    print(f"  source         : {result.source} ({result.source_kind})")
    print(f"  preset id      : {result.preset_id}")
    print(f"  always-on text : {stats['always_on_chars']:,} chars")
    print(f"  skills         : {stats['skills']}")
    print(f"  scripts        : {stats['scripts']}")
    print(f"  subagents      : {stats['subagents']}")
    print(f"  files          : {len(result.files)}")
    for warning in result.warnings:
        print(f"  ! {warning}")
    profile = opts.install_hint_profile or "web"
    print()
    print("install with:")
    print(f"  dsh plugin --profile {profile} add {result.out_dir.resolve().as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "inspect":
        return _cmd_inspect(args)
    if args.command == "convert":
        return _cmd_convert(args)
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
