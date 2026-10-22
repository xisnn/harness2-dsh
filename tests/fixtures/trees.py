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

"""Fixture builders: small Harness2 harness trees to convert in tests."""

from __future__ import annotations

from pathlib import Path

MINIMAL_SYSTEMPROMPT = "Reconcile the ledger with scripts/summarize.py.\n"

MINIMAL_GUARDRAILS = (
    "- A ledger total includes every row, negatives included.\n"
    "- The requested output format is part of the deliverable.\n"
)

MINIMAL_MEMORY = "- `amount` is signed: a negative value is a debit.\n"

MINIMAL_TOOL_GUIDANCE = "Run the helper with the shell tool; read it first.\n"

SUMMARIZE_SCRIPT = '''\
import csv
import sys
from decimal import Decimal

with open(sys.argv[1]) as source:
    amounts = [Decimal(row["amount"]) for row in csv.DictReader(source)]
total = sum(amounts, Decimal(0))
print(f"Total: {total:.2f}")
'''

LEDGER_SKILL = """\
---
name: ledger-reconciliation
description: Sum, reconcile or audit signed amounts in a ledger.
---

# Ledger reconciliation

Sum every signed row; negatives subtract. Use Decimal, then state two decimals.
"""

UNDERSCORE_SKILL = """\
---
name: ledger_math
description: Compute signed ledger totals with exact arithmetic.
---

# Ledger math

Never drop negative rows.
"""

NO_DESCRIPTION_SKILL = """\
# helper-skill

A skill whose frontmatter is missing, which DSH would silently not advertise.
"""

SUBAGENT = """\
---
name: ledger-auditor
description: Reviews a ledger reconciliation for dropped signs.
---

You audit ledger reconciliations. Check that every signed row was summed.
"""

OPENCODE_PLUGIN = """\
import { Plugin } from "@opencode-ai/plugin";

export const LedgerPlugin: Plugin = async () => ({
  "tool.execute.after": async (input) => { /* ... */ },
});
"""


def make_tree(
    root: Path,
    *,
    with_skill: bool = True,
    with_underscore_skill: bool = False,
    with_descriptionless_skill: bool = False,
    with_subagent: bool = False,
    with_script: bool = True,
    with_plugin: bool = False,
    with_skill_script: bool = False,
) -> Path:
    """Create a Harness2-shaped harness directory under `root`."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "systemprompt.md").write_text(MINIMAL_SYSTEMPROMPT, encoding="utf-8")
    (root / "guardrails.md").write_text(MINIMAL_GUARDRAILS, encoding="utf-8")
    (root / "LongTermMEMORY.md").write_text(MINIMAL_MEMORY, encoding="utf-8")
    tool_dir = root / "tool_descriptions"
    tool_dir.mkdir(exist_ok=True)
    (tool_dir / "tool_guidance.md").write_text(MINIMAL_TOOL_GUIDANCE, encoding="utf-8")

    # README stubs Harness2 writes; the converter must ignore them.
    for stub in ("skills", "sub_agents", "scripts", "plugin"):
        d = root / stub
        d.mkdir(exist_ok=True)
        (d / "README.md").write_text("<!-- stub -->\n", encoding="utf-8")

    if with_skill:
        d = root / "skills" / "ledger-reconciliation"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(LEDGER_SKILL, encoding="utf-8")
        if with_skill_script:
            sd = d / "scripts"
            sd.mkdir(exist_ok=True)
            (sd / "check.py").write_text("print('ok')\n", encoding="utf-8")

    if with_underscore_skill:
        d = root / "skills" / "ledger_math"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(UNDERSCORE_SKILL, encoding="utf-8")

    if with_descriptionless_skill:
        d = root / "skills" / "helper-skill"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(NO_DESCRIPTION_SKILL, encoding="utf-8")

    if with_subagent:
        d = root / "sub_agents" / "ledger-auditor"
        d.mkdir(parents=True, exist_ok=True)
        (d / "AGENT.md").write_text(SUBAGENT, encoding="utf-8")

    if with_script:
        (root / "scripts" / "summarize.py").write_text(SUMMARIZE_SCRIPT, encoding="utf-8")

    if with_plugin:
        (root / "plugin" / "ledger.ts").write_text(OPENCODE_PLUGIN, encoding="utf-8")

    return root
