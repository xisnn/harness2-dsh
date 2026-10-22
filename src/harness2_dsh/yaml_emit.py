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

"""Zero-dependency deterministic YAML emitter for Cordis patch files.

Only the shapes this project emits are supported: nested mappings, lists, and
scalars. Scalars that are not safe plain text are emitted as double-quoted
strings, and multi-line strings as literal block scalars. There is no dependency
on PyYAML, so `pip install harness2-dsh` needs nothing else.
"""

from __future__ import annotations

import re

# A plain scalar must not look like a YAML type, a directive, or a special value.
_PLAIN_UNSAFE_START = set("-?:,[]{}#&*!|>'\"%@` \t")
_YAML_TYPE_WORDS = {
    "true", "false", "yes", "no", "on", "off", "null", "~",
    "y", "n", "True", "False", "Yes", "No", "On", "Off", "Null", "NULL",
    "Y", "N", "TRUE", "FALSE", "YES", "NO", "ON", "OFF",
}
# YAML 1.1 booleans also accept single letters, and a bare `n`/`y` key is a
# common source of silently-retyped config, so keys use the same rule.
_INT_RE = re.compile(r"^[+-]?(0b[01_]+|0o?[0-7_]+|0x[0-9a-fA-F_]+|[0-9][0-9_]*)$")
_FLOAT_RE = re.compile(
    r"^[+-]?(\.[0-9]+|[0-9][0-9_]*(\.[0-9_]*)?)([eE][+-]?[0-9]+)?$"
)
_RESERVED_INDICATORS = re.compile(r"^(@|`)")


class JsExpression:
    """A Cordis Loader `!!js` scalar: evaluated by the Loader at mount time.

    `yaml_emit.dump` renders it as `!!js <expression>`, never as a plain string.
    """

    __slots__ = ("expression",)

    def __init__(self, expression: str):
        if not expression.strip():
            raise ValueError("a !!js expression must not be empty")
        self.expression = expression

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"JsExpression({self.expression!r})"

    def __eq__(self, other) -> bool:
        return isinstance(other, JsExpression) and other.expression == self.expression

    def __hash__(self) -> int:
        return hash((JsExpression, self.expression))


def _needs_double_quotes(value: str) -> bool:
    if value == "":
        return True
    if value in _YAML_TYPE_WORDS:
        return True
    if _INT_RE.match(value) or _FLOAT_RE.match(value):
        return True
    if value[0] in _PLAIN_UNSAFE_START:
        return True
    if _RESERVED_INDICATORS.match(value):
        return True
    # A colon-space or a trailing colon would end the plain scalar early.
    if ": " in value or value.endswith(":") or " #" in value:
        return True
    # Control characters are never valid in a plain scalar.
    if any(ord(ch) < 0x20 for ch in value):
        return True
    return False


def _double_quote(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _is_block_scalar_safe(value: str) -> bool:
    """A literal block is safe when every line is printable and none is blank-with-indent."""
    if "\r" in value:
        return False
    lines = value.split("\n")
    for line in lines:
        if any(ord(ch) < 0x20 and ch != "\t" for ch in line):
            return False
        if line and line[0] == " " and line.strip() == "":
            return False
    return True


def _emit_multiline(value: str, indent: int, prefix: str) -> list[str]:
    """Emit `value` as a literal block scalar under `prefix`."""
    body = value if value.endswith("\n") else value + "\n"
    stripped = body[:-1]
    # `|` keeps the trailing newline, `|-` strips it. We always add exactly one
    # trailing newline, so `|` matches, but only when there is no trailing blank line.
    indicator = "|" if not stripped.endswith("\n") else "|+"
    pad = " " * indent
    lines = [f"{prefix}{indicator}"]
    for line in stripped.split("\n"):
        lines.append(f"{pad}{line}" if line else "")
    return lines


def _emit_scalar(value, indent: int, prefix: str) -> list[str]:
    if isinstance(value, JsExpression):
        return [f"{prefix}!!js {value.expression}"]
    if value is None:
        return [f"{prefix}null"]
    if isinstance(value, bool):
        return [f"{prefix}{'true' if value else 'false'}"]
    if isinstance(value, (int, float)):
        return [f"{prefix}{value}"]
    text = str(value)
    if "\n" in text and _is_block_scalar_safe(text):
        return _emit_multiline(text, indent, prefix)
    if _needs_double_quotes(text):
        return [f"{prefix}{_double_quote(text)}"]
    return [f"{prefix}{text}"]


def _emit_node(value, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = _double_quote(str(key)) if _needs_double_quotes(str(key)) else str(key)
            if isinstance(child, (dict, list)):
                if not child:
                    out.append(f"{pad}{key_text}: {'{}' if isinstance(child, dict) else '[]'}")
                else:
                    out.append(f"{pad}{key_text}:")
                    _emit_node(child, indent + 2, out)
            else:
                out.extend(_emit_scalar(child, indent + 2, f"{pad}{key_text}: "))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                if isinstance(item, dict) and item:
                    # Emit the first key on the dash line for readability.
                    first = True
                    for key, child in item.items():
                        key_text = (
                            _double_quote(str(key))
                            if _needs_double_quotes(str(key))
                            else str(key)
                        )
                        lead = f"{pad}- " if first else f"{pad}  "
                        if isinstance(child, (dict, list)):
                            if not child:
                                out.append(f"{lead}{key_text}: {'{}' if isinstance(child, dict) else '[]'}")
                            else:
                                out.append(f"{lead}{key_text}:")
                                _emit_node(child, indent + 4, out)
                        else:
                            out.extend(_emit_scalar(child, indent + 4, f"{lead}{key_text}: "))
                        first = False
                else:
                    out.append(f"{pad}-")
                    _emit_node(item, indent + 2, out)
            else:
                out.extend(_emit_scalar(item, indent + 2, f"{pad}- "))
    else:  # pragma: no cover - defensive
        raise TypeError(f"cannot emit {type(value).__name__}")


def dump(document) -> str:
    """Render `document` as a YAML string ending in exactly one newline."""
    if not isinstance(document, (dict, list)):
        raise TypeError("top-level document must be a mapping or a list")
    out: list[str] = []
    _emit_node(document, 0, out)
    return "\n".join(out) + "\n"
