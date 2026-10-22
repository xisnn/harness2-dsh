# Contributing

Thanks for taking a look. This project is small on purpose: one converter, no runtime
dependencies, no network access in the test suite.

## Before you open a pull request

```bash
pip install -e '.[dev]'
pytest -q
ruff check .
```

Both must pass. If you add a conversion behaviour, add the test that would fail without it.

## What is in scope

- Reading more of what a Harness² harness tree can contain.
- Emitting better DSH declarations for components that currently map lossily.
- Clearer diagnostics when a tree cannot be converted.

## What is out of scope

- Running Harness² itself. This tool only reads its output.
- Judging whether a harness is good. Conversion is not evaluation.
- Vendoring DSH or Harness² code.

## Style

- Python 3.10+ syntax, no third-party runtime dependencies.
- Keep the YAML emitter honest: if a value would be re-typed by a YAML parser, quote it.
- Warnings must name the concrete consequence. "Skill not converted" is not enough;
  "DSH plugins are Cordis packages, not OpenCode .ts modules" is.

## Reporting a bad conversion

Open an issue with:

1. the output of `harness2-dsh inspect <path> --json`,
2. the generated `cordis.patch.yml`,
3. what DSH did when you installed it (`dsh --profile <p> --dump-config` output is ideal).
