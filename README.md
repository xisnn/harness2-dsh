# harness2-dsh

Turn a [Google Research **Harness²**](https://github.com/google-research/harness2) harness tree into a
[DeepSeek Harness (DSH)](https://github.com/deepseek-ai/deepseek-harness) **agent-preset bundle** you can
install and select like any other preset.

Harness² searches for a better agent harness around a frozen model and writes the winner to disk as a
plain directory. DSH runs agents from declarative presets. This tool is the bridge between the two: it
reads the harness directory and emits an installable DSH bundle.

```
harness2 run  ──▶  harness tree (systemprompt.md, guardrails.md, skills/, scripts/, ...)
                         │
                         ▼  harness2-dsh convert
                   DSH bundle (package.json + cordis.patch.yml + skills/ + scripts/)
                         │
                         ▼  dsh plugin --profile <p> add <bundle>
                   a selectable agent preset
```

## Why

Running Harness² end to end means OpenCode or Codex, a Linux toolchain, and model credentials. If you
already run DSH, you can keep the part that matters — the *harness it found* — and run it natively.

### Why not just install one of the existing Harness² DSH plugins?

As of 2026-10-22 there are about seven community attempts at "Harness² on DSH", all started within days
of Harness² itself and all at 0–2 stars. None appears in the official DSH plugin catalog (3,261 entries,
zero `Harness2` matches), and each falls into one of three shapes:

| Approach | What it does | Why it is not enough on its own |
|---|---|---|
| Sidecar Python driver | Reuses Harness²'s own recursion loop, drives `dsh` as the executor | POSIX-only; needs a separate venv and a second install step |
| In-tree Cordis plugin | Reimplements propose–probe–compose inside DSH | Large surface; the ones published so far ship a demo adapter, not a task executor |
| **This tool** | **Transports a harness Harness² already found into a DSH preset** | Does not run the search itself — and that is the point |

This project deliberately does **one** thing: it is the missing *transport* step. It does not reimplement
Harness², does not call a model, and has no opinion about whether a harness is good. That makes it small
enough to be correct, testable without DSH installed, and usable alongside whichever search approach you
pick — run Harness² wherever you like, then convert the winner.

It also catches two failure modes that silently produce a broken preset:

- DSH requires kebab-case skill names; Harness² accepts underscores. `ledger_math` is *silently dropped*
  by DSH. This tool renames it and rewrites the frontmatter to match.
- DSH does not advertise a skill without a `description:`. This tool synthesises one and tells you.

## Install

```bash
pip install harness2-dsh
# or, from a checkout:
pip install -e .
```

Python 3.10+, no dependencies.

## Use

```bash
# 1. see what a harness contains
harness2-dsh inspect ./library/k1/agg/accounting/harnesses/ledger-2

# 2. convert it
harness2-dsh convert ./library/k1/agg/accounting/harnesses/ledger-2 \
    --out ./bundles/ledger-recon \
    --preset-id ledger-recon \
    --name "Ledger Recon"

# 3. install and pick it in a new session
dsh plugin --profile web add ./bundles/ledger-recon
```

`convert` accepts three input shapes, so you rarely need to hunt for the tree by hand:

| You point at | It converts |
|---|---|
| a harness directory (`systemprompt.md` present) | that tree |
| a library entry (`harness/` + `EXPERIENCE.md`) | the adopted harness |
| a task run directory (`summary.json` + `harnesses/`) | the harness selection actually adopted |
| a domain library directory with one entry | that entry |

### Options

| Flag | Default | Meaning |
|---|---|---|
| `--preset-id` | from `--name` / output dir | lowercase letters, digits, hyphens |
| `--name` | the id | display name in the preset picker |
| `--description` | generated | preset description |
| `--order` | `50` | roster position |
| `--persona-mode` | `append` | `append` keeps DSH's own system prompt and adds the harness text; `replace` makes the harness text the whole system prompt |
| `--skill-path-mode` | `absolute` | `absolute` bakes the resolved skills path; `dsh-home` emits `dshHomePath(...)` for bundles installed under `$DSH_HOME` |
| `--with-subagents` | off | convert `sub_agents/` into child presets |
| `--no-scripts` | off | skip `scripts/` |
| `--profile` | `web` | profile named in the generated install hint |

## What maps to what

| Harness² component | Becomes in DSH |
|---|---|
| `systemprompt.md`, `guardrails.md`, `LongTermMEMORY.md`, `tool_descriptions/tool_guidance.md` | one always-on block in the preset's `dsh-persona` prefix, in Harness²'s own order |
| `skills/<n>/SKILL.md` + `skills/<n>/scripts/` | real DSH skills under the bundle, wired through `dsh-skill-filesystem.customSkillDirs` |
| `scripts/<n>.py` | copied into the bundle; the persona block names the absolute path |
| `sub_agents/<n>/AGENT.md` | a child agent preset plus a `dsh-tool-subagent` row (opt-in) |
| `plugin/<n>.ts` | **not converted** — OpenCode plugin modules are not Cordis plugins. Reported, never silently dropped |

### Two normalisations worth knowing

- **Skill names.** DSH requires kebab-case (`^[a-z0-9]+(?:-[a-z0-9]+)*$`); Harness² accepts underscores.
  `ledger_math` becomes `ledger-math`, and the generated `SKILL.md` frontmatter is rewritten to match.
- **Missing descriptions.** DSH silently does not advertise a skill without a `description:`. The
  converter synthesises one from the body and records a note, rather than shipping an invisible skill.

## Verify the install

```bash
dsh --profile <p> --dump-config | grep -A3 preset-<id>
```

Then start a new session and choose the preset. To confirm the skills are actually visible to the model,
ask it to load one by name.

## Development

```bash
pip install -e '.[dev]'
pytest -q
ruff check .
```

The test suite covers the YAML emitter (including `!!js` tags and literal blocks), tree parsing, every
conversion path, the run/library layout resolver, and the CLI. It needs no DSH installation and no
network.

## Limitations

- One-way. Converting back from a preset to a Harness² tree is not implemented, because a preset is a
  composition, not a file tree.
- `plugin/*.ts` has no automatic equivalent; porting is manual.
- The generated bundle is bound to the machine that produced it when `--skill-path-mode absolute` is
  used, because the skills path is absolute. Use `dsh-home` (or regenerate after moving the bundle) when
  you need it relocatable.
- The converter does not run Harness² and does not evaluate whether the harness is any good. It only
  transports what Harness² produced.

## Licence

Apache-2.0. Harness² is Apache-2.0 (Google LLC); a generated bundle contains text derived from it, so
keep the attribution when you redistribute a bundle.

This is a community tool. It is not affiliated with Google or DeepSeek.
