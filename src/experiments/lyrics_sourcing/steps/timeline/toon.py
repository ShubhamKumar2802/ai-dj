"""In-house TOON encoder for the one shape we emit (spec §4.6). Pure.

Header as `key: value` lines, then each table as `name[N]{f1,f2,...}:` followed by one
comma-separated row per item, indented two spaces. Nulls are empty fields.
"""

import dataclasses
import numbers
import re

from experiments.lyrics_sourcing.config import TimelineConfig
from experiments.lyrics_sourcing.schema import Timeline

_LOOKS_LITERAL = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$|^(true|false|null)$")
_SPECIAL_CHARS = (",", ":", '"', "\\", "\n", "\r")


def encode_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    # numbers.* (not int/float) so NumPy scalars from the analysis modules are covered too:
    # np.float64's repr is "np.float64(1.2)", and np.int64 isn't an int subclass at all.
    if isinstance(value, numbers.Integral):
        return repr(int(value))
    if isinstance(value, numbers.Real):
        return repr(float(value))
    text = str(value)
    if (
        text == ""
        or text != text.strip()
        or any(ch in text for ch in _SPECIAL_CHARS)
        or _LOOKS_LITERAL.match(text)
    ):
        escaped = (
            text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        )
        return f'"{escaped}"'
    return text


def encode_table(name: str, items: list, fields: list[str]) -> list[str]:
    lines = [f"{name}[{len(items)}]{{{','.join(fields)}}}:"]
    for item in items:
        lines.append("  " + ",".join(encode_value(getattr(item, f)) for f in fields))
    return lines


def encode_timeline(timeline: Timeline) -> str:
    lines = []
    for field in dataclasses.fields(timeline.header):
        value = encode_value(getattr(timeline.header, field.name))
        lines.append(f"{field.name}: {value}" if value else f"{field.name}:")

    row_fields = (
        [f.name for f in dataclasses.fields(type(timeline.rows[0]))] if timeline.rows else []
    )
    lines.append("")
    lines.extend(encode_table("timeline", timeline.rows, row_fields))
    lines.append("")
    lines.extend(encode_table("lyrics", timeline.lyrics, ["start", "end", "text"]))
    return "\n".join(lines) + "\n"


class ToonSerializer:
    extension = "toon"

    def __init__(self, cfg: TimelineConfig) -> None:
        self._cfg = cfg

    def serialize(self, timeline: Timeline) -> str:
        return encode_timeline(timeline)
