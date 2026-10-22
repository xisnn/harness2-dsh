# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-22

### Added

- `harness2-dsh convert`: turn a Harness² harness tree into a DSH agent-preset bundle
  (`package.json` + `cordis.patch.yml` + `skills/` + `scripts/` + `README.md`).
- `harness2-dsh inspect`: report what a harness tree contains without converting it.
- Input resolution for a harness directory, a Harness² library entry, a task run directory
  (using the harness selection actually adopted), and a single-entry domain library.
- Component mapping: the four always-on files become one persona block in Harness²'s order;
  skills become real DSH skills wired through `customSkillDirs`; scripts ship with the bundle
  and are named by absolute path; `sub_agents/` becomes child presets plus a
  `dsh-tool-subagent` row when `--with-subagents` is passed.
- Skill-name normalisation to DSH's kebab-case grammar, with the generated `SKILL.md`
  frontmatter rewritten to match.
- A synthesised description for a skill that has none, because DSH silently does not
  advertise such a skill.
- An explicit warning for `plugin/*.ts`, which has no automatic DSH equivalent.
- A zero-dependency YAML emitter that quotes values a YAML parser would re-type and renders
  Cordis `!!js` loader expressions.
- 72 tests covering the emitter, tree parsing, every conversion path, input resolution, and
  the CLI. No network and no DSH installation required.

[Unreleased]: https://github.com/example/harness2-dsh/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/example/harness2-dsh/releases/tag/v0.1.0
