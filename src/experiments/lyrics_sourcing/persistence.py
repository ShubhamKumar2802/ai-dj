"""Step output persistence (spec §4.8): save_step / load_step, plus the JSON helpers.

`from_dict` rebuilds any contract from its JSON form by walking the dataclass type hints,
so nested dataclasses (including production ones like RawFeatures/CueDerivationResult)
come back as real instances rather than dicts — the same problem
feature_extractor.cache._read solves by hand for RawFeatures alone.
"""

import dataclasses
import json
import types
import typing
from pathlib import Path
from typing import Any, Literal, TypeVar, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel

T = TypeVar("T")


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    if isinstance(obj, dict):
        return {str(key): to_jsonable(value) for key, value in obj.items()}
    return obj


def from_dict(tp: Any, data: Any) -> Any:
    if data is None:
        return None

    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        non_none = [arg for arg in get_args(tp) if arg is not type(None)]
        return from_dict(non_none[0], data) if len(non_none) == 1 else data
    if origin is list:
        (item_type,) = get_args(tp)
        return [from_dict(item_type, item) for item in data]
    if origin is dict:
        return dict(data)
    if origin is tuple:
        return tuple(data)
    if origin is Literal or tp is Any or tp is typing.Any:
        return data
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return tp.model_validate(data)
    if dataclasses.is_dataclass(tp):
        hints = get_type_hints(tp)
        return tp(
            **{
                f.name: from_dict(hints[f.name], data[f.name])
                for f in dataclasses.fields(tp)
                if f.name in data
            }
        )
    return data


def save_step(out_dir: Path, name: str, obj: Any) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(to_jsonable(obj), indent=2, ensure_ascii=False))
    return path


def load_step(out_dir: Path, name: str, tp: type[T]) -> T:
    path = out_dir / f"{name}.json"
    return from_dict(tp, json.loads(path.read_text()))
