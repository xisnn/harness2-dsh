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

"""Convert a Harness2 harness tree into a DSH agent-preset bundle.

The output is an ordinary DSH bundle: a package directory whose `package.json`
declares `dsh.bundle.patch`, plus the patch file that inserts one
`@deepseek-ai/dsh-agent-preset` row. Installing it with `plugin_manager` or
`dsh plugin --profile <p> add <dir>` adds a selectable agent preset.

Component mapping (Harness2 -> DSH):

    systemprompt.md + guardrails.md + LongTermMEMORY.md + tool_guidance.md
        -> the preset's `dsh-persona` prefix (always-on text, one block)
    skills/<n>/SKILL.md (+ scripts/)
        -> real DSH skills under the bundle, wired through
           `dsh-skill-filesystem.customSkillDirs`
    sub_agents/<n>/AGENT.md
        -> a child agent preset plus a `dsh-tool-subagent` row (opt-in)
    scripts/<n>.py
        -> copied into the bundle and named in the persona block
    plugin/<n>.ts
        -> NOT converted (OpenCode modules are not Cordis plugins); reported

Nothing here mutates the input tree.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import tree as harness_tree
from . import yaml_emit

# Tools a converted preset gets. These are the same rows the shipped `standard`
# preset mounts, minus the ones that make no sense for a benchmark-derived
# harness (plan mode, goals, scheduling) and minus subagent rows unless asked for.
BASE_TOOL_ROWS: tuple[dict, ...] = (
    {"id": "agent-instructions", "name": "@deepseek-ai/dsh-agent-instructions", "config": {"maxBytes": 65536}},
    {"id": "time-context", "name": "@deepseek-ai/dsh-time-context"},
    {"id": "tool-bash", "name": "@deepseek-ai/dsh-tool-bash", "disabled": "platform-win32"},
    {"id": "tool-pwsh", "name": "@deepseek-ai/dsh-tool-pwsh", "disabled": "platform-not-win32"},
    {"id": "tool-fs", "name": "@deepseek-ai/dsh-tool-fs"},
    {"id": "tool-fs-search", "name": "@deepseek-ai/dsh-tool-fs-search", "config": {"sampleOverCapGlobResults": False}},
    {"id": "tool-jobs", "name": "@deepseek-ai/dsh-tool-jobs"},
    {"id": "tool-todo", "name": "@deepseek-ai/dsh-tool-todo"},
)

_PLATFORM_DISABLED = {
    "platform-win32": "process.platform === 'win32'",
    "platform-not-win32": "process.platform !== 'win32'",
}

_ID_SAFE = re.compile(r"[^a-z0-9-]+")


@dataclass
class Options:
    """Everything the converter needs besides the input tree."""

    preset_id: str
    preset_name: str = ""
    description: str = ""
    order: int = 50
    #: `append` keeps DSH's own system prompt and adds the harness text after it;
    #: `replace` makes the harness text the whole system prompt (Harness2's
    #: always-on block then stands alone, which is closer to the upstream setup).
    persona_mode: str = "append"
    #: How the preset locates this bundle's `skills/` directory:
    #:
    #: * ``package`` (default) — resolve the installed package by name through the
    #:   profile's own `node_modules`, using the Loader's ``baseUrl``. The bundle
    #:   can be moved or handed to another machine and still works.
    #: * ``absolute`` — bake the resolved path in. Simplest, but only valid on the
    #:   machine that generated it.
    #: * ``dsh-home`` — emit ``dshHomePath(...)``; only valid when the bundle is
    #:   installed under ``$DSH_HOME``.
    skill_path_mode: str = "package"
    with_subagents: bool = False
    with_scripts: bool = True
    install_hint_profile: str = ""


@dataclass
class Conversion:
    """The generated bundle, plus what was skipped and why."""

    out_dir: Path
    preset_id: str
    harness: harness_tree.Harness
    source: Path | None = None
    source_kind: str = ""
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def preset_row_id(self) -> str:
        return f"preset-{self.preset_id}"


def _slug(text: str) -> str:
    folded = _ID_SAFE.sub("-", text.strip().lower()).strip("-")
    return folded or "harness"


def normalise_preset_id(raw: str) -> str:
    """Preset ids are lowercase letters, digits and hyphens."""
    folded = _ID_SAFE.sub("-", raw.strip().lower()).strip("-")
    if not folded:
        raise ValueError(f"preset id {raw!r} is empty after normalisation")
    if not folded[0].isalpha():
        folded = f"h-{folded}"
    return folded


def _persona_block(
    harness: harness_tree.Harness,
    opts: Options,
    scripts_ref: str | None,
) -> str:
    """Build the always-on text the preset injects.

    Harness2's four always-on files become one block, in Harness2's own order, so
    the relative order of prompt / guardrails / memory / tool guidance survives.
    """
    parts: list[str] = []
    labels = {
        "systemprompt.md": "",
        "guardrails.md": "# GUARDRAILS",
        "LongTermMEMORY.md": "# MEMORY",
        "tool_descriptions/tool_guidance.md": "# TOOL GUIDANCE",
    }
    for rel in harness_tree.ALWAYS_ON:
        body = harness.always_on.get(rel, "").strip()
        if not body:
            continue
        label = labels[rel]
        parts.append(f"{label}\n\n{body}" if label else body)

    if scripts_ref is not None and harness.scripts:
        names = ", ".join(f"`{name}`" for name in sorted(harness.scripts))
        parts.append(
            "# HELPER SCRIPTS\n\n"
            f"Deterministic helpers ship with this preset at {scripts_ref}: {names}.\n"
            "Run them with the shell tool. They are plain Python; read one before relying on it."
        )

    if harness.skills:
        # Harness2 requires every skill to be named in always-on text or the
        # proposal is rejected. Keep that invariant: advertise each trigger.
        lines = [
            "- When the situation matches its description, load the "
            f"`{skill.name}` skill: {skill.description}"
            for skill in sorted(harness.skills, key=lambda s: s.name)
        ]
        parts.append("# AVAILABLE SKILLS\n\n" + "\n".join(lines))

    return "\n\n---\n\n".join(parts)


def _skill_files(harness: harness_tree.Harness, skills_root: Path) -> list[Path]:
    """Write one DSH skill directory per Harness2 skill. Returns the written paths."""
    written: list[Path] = []
    for skill in harness.skills:
        target = skills_root / skill.name
        target.mkdir(parents=True, exist_ok=True)
        frontmatter = (
            "---\n"
            f"name: {skill.name}\n"
            f"description: {_yaml_inline(skill.description)}\n"
            "---\n"
        )
        body = skill.body if skill.body.strip() else f"# {skill.name}\n"
        skill_md = target / "SKILL.md"
        skill_md.write_text(frontmatter + body, encoding="utf-8")
        written.append(skill_md)
        for rel, content in skill.scripts.items():
            dest = target / "scripts" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            written.append(dest)
    return written


def _yaml_inline(text: str) -> str:
    """A single-line YAML scalar safe inside a frontmatter `description:`."""
    flat = " ".join(text.split())
    if not flat:
        return '""'
    if any(ch in flat for ch in ':#"\'') or flat[0] in "-?:,[]{}#&*!|>'\"%@`":
        escaped = flat.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return flat


def _script_files(harness: harness_tree.Harness, scripts_root: Path) -> list[Path]:
    written: list[Path] = []
    for name, content in sorted(harness.scripts.items()):
        dest = scripts_root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(dest)
    return written


def _plugin_row(row: dict) -> dict:
    """Translate the internal `disabled` shorthand into a real loader expression."""
    out: dict = {}
    for key, value in row.items():
        if key == "disabled" and isinstance(value, str):
            expression = _PLATFORM_DISABLED.get(value)
            if expression is None:
                raise ValueError(f"unknown disabled shorthand {value!r}")
            out[key] = yaml_emit.JsExpression(expression)
        else:
            out[key] = value
    return out


def convert(src: Path, out_dir: Path, opts: Options) -> Conversion:
    """Convert the harness tree at `src` into a DSH bundle at `out_dir`.

    `src` may also be a Harness2 library entry or a task run directory; see
    `tree.resolve_harness_root` for how the adopted harness is located.
    """
    opts.preset_id = normalise_preset_id(opts.preset_id)
    harness_root, how = harness_tree.resolve_harness_root(Path(src))
    harness = harness_tree.load(harness_root)

    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty {out_dir}")

    pkg_name = f"dsh-harness2-{opts.preset_id}"
    bundle_dir = out_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)

    conv = Conversion(
        out_dir=bundle_dir,
        preset_id=opts.preset_id,
        harness=harness,
        source=harness_root,
        source_kind=how,
    )
    conv.warnings.extend(harness.warnings)

    skills_root = bundle_dir / "skills"
    scripts_root = bundle_dir / "scripts" if opts.with_scripts and harness.scripts else None

    written: list[Path] = []
    if harness.skills:
        written.extend(_skill_files(harness, skills_root))
    if scripts_root is not None:
        written.extend(_script_files(harness, scripts_root))

    # How the persona text names the helper scripts. In the portable modes the
    # bundle's own location is not known when the text is composed, so describe
    # where to look rather than baking in a path that would go stale.
    if scripts_root is None:
        scripts_ref = None
    elif opts.skill_path_mode == "absolute":
        scripts_ref = scripts_root.resolve().as_posix()
    else:
        scripts_ref = f"`{pkg_name}` package, `scripts/` subdirectory"

    persona_text = _persona_block(harness, opts, scripts_ref)

    # ── preset plugin rows ────────────────────────────────────────────────────
    plugins: list[dict] = [
        {
            "id": "persona",
            "name": "@deepseek-ai/dsh-persona",
            "config": {
                "prefix": persona_text,
                "complete": opts.persona_mode == "replace",
                "includeRuntimeContext": True,
            },
        }
    ]
    plugins.extend(_plugin_row(row) for row in BASE_TOOL_ROWS)

    if harness.skills:
        if opts.skill_path_mode == "dsh-home":
            skills_value = yaml_emit.JsExpression(
                f"dshHomePath('{_dsh_home_rel(bundle_dir, skills_root)}')"
            )
        elif opts.skill_path_mode == "package":
            skills_value = yaml_emit.JsExpression(_package_resolve_expression(pkg_name))
        elif opts.skill_path_mode == "absolute":
            skills_value = skills_root.resolve().as_posix()
        else:
            raise ValueError(
                f"unknown skill_path_mode {opts.skill_path_mode!r}; "
                "expected package, absolute or dsh-home"
            )
        plugins.append(
            {
                "id": "skill-filesystem",
                "name": "@deepseek-ai/dsh-skill-filesystem",
                "config": {"customSkillDirs": [skills_value]},
            }
        )
        plugins.append({"id": "tool-skill", "name": "@deepseek-ai/dsh-tool-skill"})

    sub_presets: list[dict] = []
    if opts.with_subagents and harness.subagents:
        allowed: list[str] = []
        for agent in harness.subagents:
            child_id = f"{opts.preset_id}--{agent.name}"
            allowed.append(child_id)
            sub_presets.append(
                {
                    "insert": [
                        {
                            "id": f"preset-{child_id}",
                            "name": "@deepseek-ai/dsh-agent-preset",
                            "config": {
                                "id": child_id,
                                "name": f"{opts.preset_name or opts.preset_id} / {agent.name}",
                                "description": agent.description,
                                "order": opts.order + 1,
                                "plugins": [
                                    {
                                        "id": "persona",
                                        "name": "@deepseek-ai/dsh-persona",
                                        "config": {"prefix": agent.body.strip() or agent.description},
                                    },
                                    *(_plugin_row(row) for row in BASE_TOOL_ROWS),
                                ],
                            },
                        }
                    ]
                }
            )
        plugins.append(
            {
                "id": "delegation",
                "name": "cordis:group",
                "group": True,
                "config": [
                    {"id": "tool-subagent", "name": "@deepseek-ai/dsh-tool-subagent",
                     "config": {"provider": "spawn", "toolName": "subagent",
                                "allowedAgentPresets": allowed}},
                ],
            }
        )

    declaration = {
        "insert": [
            {
                "id": conv.preset_row_id,
                "name": "@deepseek-ai/dsh-agent-preset",
                "config": {
                    "id": opts.preset_id,
                    "name": opts.preset_name or opts.preset_id,
                    "description": opts.description or _default_description(harness),
                    "order": opts.order,
                    "plugins": plugins,
                },
            }
        ]
    }
    document = [declaration, *sub_presets]

    patch_path = bundle_dir / "cordis.patch.yml"
    patch_path.write_text(
        "# Generated by harness2-dsh. Do not edit by hand: regenerate from the harness tree.\n"
        + yaml_emit.dump(document),
        encoding="utf-8",
    )
    written.append(patch_path)

    manifest = {
        "name": pkg_name,
        "version": "1.0.0",
        "private": True,
        "description": opts.description or _default_description(harness),
        "type": "module",
        "dsh": {"bundle": {"patch": "./cordis.patch.yml"}},
        "license": "Apache-2.0",
    }
    manifest_path = bundle_dir / "package.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    written.append(manifest_path)

    readme_path = bundle_dir / "README.md"
    readme_path.write_text(_bundle_readme(conv, opts, pkg_name), encoding="utf-8")
    written.append(readme_path)

    conv.files = sorted(written)
    return conv


def _dsh_home_rel(bundle_dir: Path, skills_root: Path) -> str:
    """The bundle's path relative to $DSH_HOME, for a `dshHomePath(...)` expression."""
    parts = bundle_dir.resolve().parts
    if "profiles" in parts:
        idx = parts.index("profiles")
        return "/".join(parts[idx + 2 :] + [skills_root.name])
    return skills_root.name


def _package_resolve_expression(pkg_name: str) -> str:
    """A Loader expression that finds this bundle's `skills/` by package name.

    The Loader evaluates `!!js` scalars in the profile context, where `baseUrl` is
    the profile directory's URL. Resolving the bundle's own package.json from there
    asks Node's resolver to find the installed package wherever the package manager
    actually put it, so the result survives moving the bundle to another machine.

    This mirrors what the shipped `standard` preset does for its bundled skills.
    """
    return (
        "process.getBuiltinModule('node:path').join("
        "process.getBuiltinModule('node:path').dirname("
        "process.getBuiltinModule('node:module')"
        f".createRequire(baseUrl).resolve('{pkg_name}/package.json')"
        "), 'skills')"
    )


def _default_description(harness: harness_tree.Harness) -> str:
    bits = []
    if harness.skills:
        bits.append(f"{len(harness.skills)} skill(s)")
    if harness.scripts:
        bits.append(f"{len(harness.scripts)} script(s)")
    suffix = f" ({', '.join(bits)})" if bits else ""
    return f"Harness2-derived agent preset{suffix}"


def _bundle_readme(conv: Conversion, opts: Options, pkg_name: str) -> str:
    stats = conv.harness.summary()
    lines = [
        f"# {opts.preset_name or opts.preset_id}",
        "",
        "Generated by [`harness2-dsh`](https://github.com/xisnn/harness2-dsh) from a "
        "Google Research Harness² harness tree.",
        "",
        "## Install",
        "",
        "```bash",
        f"dsh plugin --profile {opts.install_hint_profile or 'web'} add {conv.out_dir.resolve().as_posix()}",
        "```",
        "",
        "Then pick the preset in a new session. Remove it with "
        f"`dsh plugin --profile {opts.install_hint_profile or 'web'} remove {pkg_name}`.",
        "",
        "## What is inside",
        "",
        f"- preset id: `{opts.preset_id}`",
        f"- source: `{conv.source.as_posix() if conv.source else '?'}`"
        + (f" ({conv.source_kind})" if conv.source_kind else ""),
        f"- always-on text: {stats['always_on_chars']:,} characters",
        f"- skills: {stats['skills']}",
        f"- scripts: {stats['scripts']}",
        f"- subagents: {stats['subagents']}"
        + ("" if opts.with_subagents else " (not converted; pass --with-subagents)"),
        "",
    ]
    if conv.warnings:
        lines += ["## Conversion notes", ""]
        lines += [f"- {w}" for w in conv.warnings]
        lines += [""]
    lines += [
        "## Regenerate",
        "",
        "```bash",
        f"harness2-dsh convert <harness-dir> --out {conv.out_dir.name} --preset-id {opts.preset_id}",
        "```",
        "",
        "## Licence",
        "",
        "Apache-2.0. Harness² is Apache-2.0 (Google LLC); this generated bundle contains "
        "text derived from it.",
        "",
    ]
    return "\n".join(lines)
