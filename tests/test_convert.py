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

"""Tests for converting a harness tree into a DSH bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import trees  # noqa: E402

from harness2_dsh import convert as convert_mod  # noqa: E402


def _opts(**kw) -> convert_mod.Options:
    base = {"preset_id": "ledger-recon", "preset_name": "Ledger Recon"}
    base.update(kw)
    return convert_mod.Options(**base)


def _convert(tmp_path, src_kw=None, **opts_kw):
    src = trees.make_tree(tmp_path / "src", **(src_kw or {}))
    out = tmp_path / "out"
    return convert_mod.convert(src, out, _opts(**opts_kw)), out


def test_bundle_layout(tmp_path):
    result, out = _convert(tmp_path, {"with_skill_script": True})
    assert (out / "package.json").is_file()
    assert (out / "cordis.patch.yml").is_file()
    assert (out / "README.md").is_file()
    assert (out / "skills" / "ledger-reconciliation" / "SKILL.md").is_file()
    assert (out / "skills" / "ledger-reconciliation" / "scripts" / "check.py").is_file()
    assert (out / "scripts" / "summarize.py").is_file()
    assert result.preset_id == "ledger-recon"


def test_manifest_declares_a_bundle_patch(tmp_path):
    _, out = _convert(tmp_path)
    manifest = json.loads((out / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "dsh-harness2-ledger-recon"
    assert manifest["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert manifest["private"] is True


def test_patch_inserts_one_preset_row(tmp_path):
    _, out = _convert(tmp_path)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "- insert:" in patch
    assert "id: preset-ledger-recon" in patch
    assert 'name: "@deepseek-ai/dsh-agent-preset"' in patch
    assert "id: ledger-recon" in patch
    assert patch.count("@deepseek-ai/dsh-agent-preset") == 1


def test_always_on_components_become_one_persona_block(tmp_path):
    _, out = _convert(tmp_path)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "name: \"@deepseek-ai/dsh-persona\"" in patch
    for marker in ("# GUARDRAILS", "# MEMORY", "# TOOL GUIDANCE", "# AVAILABLE SKILLS"):
        assert marker in patch


def test_scripts_are_named_in_the_persona_block(tmp_path):
    _, out = _convert(tmp_path)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "# HELPER SCRIPTS" in patch
    assert "summarize.py" in patch


def test_absolute_mode_names_scripts_by_full_path(tmp_path):
    _, out = _convert(tmp_path, skill_path_mode="absolute")
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    expected = (out / "scripts").resolve().as_posix()
    assert expected in patch


def test_skills_are_wired_through_custom_skill_dirs(tmp_path):
    _, out = _convert(tmp_path)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "customSkillDirs" in patch
    assert 'name: "@deepseek-ai/dsh-tool-skill"' in patch


def test_default_skill_path_mode_resolves_the_package_portably(tmp_path):
    """The default must not bake in an absolute path: the bundle has to be movable."""
    _, out = _convert(tmp_path)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "!!js" in patch
    assert "createRequire(baseUrl)" in patch
    assert "dsh-harness2-ledger-recon/package.json" in patch
    # No absolute path from this machine may leak into the generated patch.
    assert out.resolve().as_posix() not in patch


def test_absolute_skill_path_mode_bakes_the_path(tmp_path):
    _, out = _convert(tmp_path, skill_path_mode="absolute")
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert (out / "skills").resolve().as_posix() in patch
    assert "createRequire" not in patch


def test_no_skills_means_no_skill_rows(tmp_path):
    _, out = _convert(tmp_path, {"with_skill": False})
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "customSkillDirs" not in patch
    assert "@deepseek-ai/dsh-tool-skill" not in patch


def test_skill_frontmatter_is_rewritten_to_dsh_grammar(tmp_path):
    _, out = _convert(tmp_path, {"with_skill": False, "with_underscore_skill": True})
    skill_md = (out / "skills" / "ledger-math" / "SKILL.md").read_text(encoding="utf-8")
    assert skill_md.startswith("---\nname: ledger-math\n")
    assert "description:" in skill_md
    # The original frontmatter must not survive as a second block.
    assert skill_md.count("---") == 2


def test_persona_replace_mode_sets_complete(tmp_path):
    _, out = _convert(tmp_path, persona_mode="replace")
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "complete: true" in patch


def test_persona_append_mode_leaves_complete_false(tmp_path):
    _, out = _convert(tmp_path)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "complete: false" in patch


def test_platform_disabled_uses_js_expressions(tmp_path):
    _, out = _convert(tmp_path)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "disabled: !!js process.platform === 'win32'" in patch
    assert "disabled: !!js process.platform !== 'win32'" in patch


def test_subagents_are_skipped_unless_asked(tmp_path):
    _, out = _convert(tmp_path, {"with_subagent": True})
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "preset-ledger-recon--ledger-auditor" not in patch
    assert "@deepseek-ai/dsh-tool-subagent" not in patch


def test_subagents_become_child_presets_when_asked(tmp_path):
    _, out = _convert(tmp_path, {"with_subagent": True}, with_subagents=True)
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "id: preset-ledger-recon--ledger-auditor" in patch
    assert "@deepseek-ai/dsh-tool-subagent" in patch
    assert "allowedAgentPresets" in patch
    assert "ledger-recon--ledger-auditor" in patch


def test_scripts_can_be_disabled(tmp_path):
    _, out = _convert(tmp_path, with_scripts=False)
    assert not (out / "scripts").exists()
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "# HELPER SCRIPTS" not in patch

def test_dsh_home_skill_path_mode_emits_js_expression(tmp_path):
    _, out = _convert(tmp_path, skill_path_mode="dsh-home")
    patch = (out / "cordis.patch.yml").read_text(encoding="utf-8")
    assert "!!js dshHomePath(" in patch


def test_conversion_is_deterministic(tmp_path):
    """Same input, same options, same bundle bytes — apart from the out path itself."""
    src = tmp_path / "src"
    trees.make_tree(src)
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    convert_mod.convert(src, out_a, _opts())
    convert_mod.convert(src, out_b, _opts())
    a = (out_a / "cordis.patch.yml").read_text(encoding="utf-8")
    b = (out_b / "cordis.patch.yml").read_text(encoding="utf-8")
    # The only permitted difference is the absolute path baked into the bundle.
    assert a.replace(out_a.resolve().as_posix(), "<OUT>") == b.replace(
        out_b.resolve().as_posix(), "<OUT>"
    )


def test_input_tree_is_not_modified(tmp_path):
    src = trees.make_tree(tmp_path / "src")
    before = {p: p.read_bytes() for p in src.rglob("*") if p.is_file()}
    convert_mod.convert(src, tmp_path / "out", _opts())
    after = {p: p.read_bytes() for p in src.rglob("*") if p.is_file()}
    assert before == after


def test_refuses_to_overwrite_non_empty_output(tmp_path):
    src = trees.make_tree(tmp_path / "src")
    out = tmp_path / "out"
    out.mkdir()
    (out / "existing.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        convert_mod.convert(src, out, _opts())


def test_preset_id_is_normalised(tmp_path):
    src = trees.make_tree(tmp_path / "src")
    result = convert_mod.convert(src, tmp_path / "out", _opts(preset_id="My Ledger_Preset"))
    assert result.preset_id == "my-ledger-preset"


def test_preset_id_starting_with_a_digit_is_prefixed(tmp_path):
    src = trees.make_tree(tmp_path / "src")
    result = convert_mod.convert(src, tmp_path / "out", _opts(preset_id="2fast"))
    assert result.preset_id == "h-2fast"


def test_opencode_plugin_warning_reaches_the_conversion(tmp_path):
    result, _ = _convert(tmp_path, {"with_plugin": True})
    assert any("not converted" in w for w in result.warnings)


def test_bundle_readme_lists_the_install_command(tmp_path):
    result, out = _convert(tmp_path, install_hint_profile="h2test")
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "dsh plugin --profile h2test add" in readme
    assert result.out_dir.resolve().as_posix() in readme
