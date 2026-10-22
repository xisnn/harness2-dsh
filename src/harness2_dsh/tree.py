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

"""Read a Harness2 harness tree from disk.

The on-disk shape is the one `harness2.core.tree` reads and writes: a directory
whose editable components are `systemprompt.md`, `guardrails.md`,
`LongTermMEMORY.md`, `tool_descriptions/tool_guidance.md`,
`skills/<name>/SKILL.md`, `sub_agents/<name>/AGENT.md`, `scripts/<name>.py`
and `plugin/<name>.ts`.

This module is deliberately independent of Harness2 itself: it parses the same
files by path, so it works whether the tree came from a Harness2 run, a
`library/` entry, or was hand-written. That keeps the converter installable with
no Python dependency on the upstream repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Always-on components, in the order Harness2 concatenates them.
ALWAYS_ON = (
    "systemprompt.md",
    "guardrails.md",
    "LongTermMEMORY.md",
    "tool_descriptions/tool_guidance.md",
)

# README stubs Harness2 writes to explain a component; never part of the tree.
_STUB_SUFFIX = "README.md"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.M)
_DESC_RE = re.compile(r"^description:\s*(.+?)\s*$", re.M)

# DSH's public skill-name grammar: @deepseek-ai/dsh-skill SKILL_NAME.
_DSH_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def dsh_skill_name(raw: str) -> str:
    """Normalise a Harness2 skill/subagent directory name to DSH's kebab-case grammar.

    Harness2 accepts underscores; DSH does not (`^[a-z0-9]+(?:-[a-z0-9]+)*$`).
    Anything outside the grammar is folded to hyphens and collapsed.
    """
    lowered = raw.strip().lower()
    folded = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not folded:
        raise ValueError(f"skill name {raw!r} has no characters usable in a DSH skill name")
    return folded


def is_dsh_skill_name(name: str) -> bool:
    return bool(_DSH_SKILL_NAME_RE.match(name))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML frontmatter from body. Only flat `key: value` pairs are read."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip("'\"")
    return meta, text[m.end() :]


def _first_match(rx: re.Pattern[str], text: str) -> str:
    m = rx.search(text)
    return m.group(1).strip().strip("'\"") if m else ""


@dataclass
class Skill:
    raw_name: str
    name: str
    description: str
    body: str
    scripts: dict[str, str] = field(default_factory=dict)


@dataclass
class Subagent:
    raw_name: str
    name: str
    description: str
    body: str


@dataclass
class Harness:
    """One Harness2 harness tree, parsed and normalised for DSH."""

    root: Path
    always_on: dict[str, str] = field(default_factory=dict)
    skills: list[Skill] = field(default_factory=list)
    subagents: list[Subagent] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)
    plugins: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def always_on_text(self) -> str:
        parts = [self.always_on.get(rel, "").strip() for rel in ALWAYS_ON]
        return "\n\n".join(p for p in parts if p)

    def summary(self) -> dict[str, int]:
        return {
            "always_on_chars": len(self.always_on_text),
            "skills": len(self.skills),
            "subagents": len(self.subagents),
            "scripts": len(self.scripts),
            "plugins": len(self.plugins),
        }


def _walk_component_dirs(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)


def load(root: Path) -> Harness:
    """Parse a Harness2 harness directory. Raises ValueError when it is not a tree."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"harness directory does not exist: {root}")
    present = [rel for rel in ALWAYS_ON if (root / rel).is_file()]
    if not present:
        raise ValueError(
            f"{root} is not a Harness2 harness tree: none of the always-on components "
            f"({', '.join(ALWAYS_ON)}) is present"
        )

    harness = Harness(root=root)

    for rel in ALWAYS_ON:
        path = root / rel
        harness.always_on[rel] = _read(path) if path.is_file() else ""

    for skill_dir in _walk_component_dirs(root / "skills"):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        text = _read(skill_md)
        meta, body = parse_frontmatter(text)
        raw = meta.get("name") or _first_match(_NAME_RE, text) or skill_dir.name
        try:
            name = dsh_skill_name(raw)
        except ValueError as exc:
            harness.warnings.append(str(exc))
            continue
        if name != raw:
            harness.warnings.append(
                f"skill {raw!r} renamed to {name!r} (DSH skill names are kebab-case)"
            )
        description = meta.get("description") or _first_match(_DESC_RE, text)
        if not description:
            # DSH drops a skill with no description without telling the model.
            harness.warnings.append(
                f"skill {name!r} has no description; DSH would not advertise it, "
                "so the converted preset supplies one from the skill body"
            )
            description = _fallback_description(body, name)
        scripts: dict[str, str] = {}
        for path in sorted((skill_dir / "scripts").rglob("*")) if (skill_dir / "scripts").is_dir() else []:
            if path.is_file():
                scripts[path.relative_to(skill_dir / "scripts").as_posix()] = _read(path)
        harness.skills.append(
            Skill(raw_name=raw, name=name, description=description, body=body, scripts=scripts)
        )

    for agent_dir in _walk_component_dirs(root / "sub_agents"):
        agent_md = agent_dir / "AGENT.md"
        if not agent_md.is_file():
            continue
        text = _read(agent_md)
        meta, body = parse_frontmatter(text)
        raw = meta.get("name") or _first_match(_NAME_RE, text) or agent_dir.name
        try:
            name = dsh_skill_name(raw)
        except ValueError as exc:
            harness.warnings.append(str(exc))
            continue
        description = meta.get("description") or _first_match(_DESC_RE, text)
        if not description:
            description = _fallback_description(body, name)
        harness.subagents.append(
            Subagent(raw_name=raw, name=name, description=description, body=body)
        )

    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.glob("*.py")):
            if path.name == _STUB_SUFFIX:
                continue
            harness.scripts[path.name] = _read(path)

    plugin_dir = root / "plugin"
    if plugin_dir.is_dir():
        for path in sorted(plugin_dir.glob("*.ts")):
            harness.plugins.append(path.name)
        if harness.plugins:
            harness.warnings.append(
                f"{len(harness.plugins)} Harness2 plugin file(s) were not converted: DSH plugins "
                "are Cordis packages, not OpenCode .ts modules. Port them by hand if needed."
            )

    return harness


def _fallback_description(body: str, name: str) -> str:
    """A short description for a component that has none."""
    for line in body.splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text[:200]
    return f"The {name} skill."


def _looks_like_harness(path: Path) -> bool:
    return any((path / rel).is_file() for rel in ALWAYS_ON)


def resolve_harness_root(path: Path) -> tuple[Path, str]:
    """Find the harness directory a caller meant, and say how it was found.

    Accepts, in order of specificity:

    * a harness directory itself (any always-on component present);
    * a Harness2 library entry (`<task>/harness/` beside `EXPERIENCE.md`);
    * a Harness2 task run directory (`summary.json` plus `harnesses/<label>/`),
      in which case the harness the run actually adopted is chosen.

    Returns `(root, explanation)`.
    """
    path = Path(path)
    if not path.is_dir():
        raise ValueError(f"path does not exist: {path}")

    if _looks_like_harness(path):
        return path, "harness directory"

    # A library entry: <domain>/harnesses/<task>/{harness, EXPERIENCE.md}
    entry_harness = path / "harness"
    if (path / "EXPERIENCE.md").is_file() and _looks_like_harness(entry_harness):
        return entry_harness, "library entry (adopted harness)"

    # A task run directory: summary.json records what selection adopted.
    summary = path / "summary.json"
    if summary.is_file():
        import json

        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{summary} is not readable JSON: {exc}") from exc
        harnesses = path / "harnesses"
        selections = data.get("selections") or {}
        # Prefer the mode recorded in the summary; fall back to any mode with a choice.
        for mode, record in sorted(selections.items()):
            chosen = (record or {}).get("chosen_label")
            if chosen and (harnesses / chosen).is_dir():
                return harnesses / chosen, f"adopted harness from {summary.name} ({mode}={chosen})"
        # No selection recorded (e.g. a stage-only run): use the last final harness.
        finals: list[str] = []
        for mode_record in (data.get("modes") or {}).values():
            finals.extend((mode_record or {}).get("finals") or [])
        for label in reversed(finals):
            if (harnesses / label).is_dir():
                return harnesses / label, f"final harness from {summary.name} ({label})"
        raise ValueError(
            f"{summary} records no adopted or final harness; point at a harness directory instead"
        )

    # A library/domain directory with exactly one entry.
    entries = sorted(p for p in (path / "harnesses").glob("*") if p.is_dir())
    if len(entries) == 1 and _looks_like_harness(entries[0] / "harness"):
        return entries[0] / "harness", "the only library entry"

    raise ValueError(
        f"could not find a harness tree in {path}: expected a harness directory, a "
        "library entry (harness/ + EXPERIENCE.md), or a task run directory with summary.json"
    )
