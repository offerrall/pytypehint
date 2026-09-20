import re
from dataclasses import dataclass, field
from datetime import date, time
from typing import ClassVar

from pytypehint.atoms import Label, Description, OptionalToggle
from pytypehint.errors import SchemaTypeError, SchemaValueError, _prefixed, _renote
from pytypehint.shapes import (
    Date, EnumShape, Float, List, NoneShape, Shape, Time, Tuple,
    duplicate_discriminators, duplicate_options,
)
from pytypehint.utils import MISSING, check_opt
from pytypehint.validation import accepted, check_options_value, value_branch

_TYPE = "$type"
_VALUE = "$value"


@dataclass(frozen=True)
class _Factory:
    fn: object


@dataclass(frozen=True, kw_only=True, eq=False)
class Struct(Shape):
    cls: type
    fields: "tuple[Field, ...]"

    discriminator: ClassVar[str] = "struct"

    @property
    def pytype(self) -> type:  # type: ignore[override]
        return self.cls

    def __post_init__(self):
        if not isinstance(self.cls, type):
            raise TypeError(f"Struct.cls must be a class, got {type(self.cls).__name__}")

        if type(self.fields) is not tuple or any(type(f) is not Field for f in self.fields):
            raise TypeError("Struct.fields must be a tuple of Field")

        names = [f.name for f in self.fields]

        if len(names) != len(set(names)):
            raise ValueError(f"duplicate field names in {self.cls.__name__}")

    def _check(self, value) -> None:
        if type(value) is not self.cls:
            raise SchemaTypeError(f"expected {self.cls.__name__}, got {type(value).__name__}")

        for f in self.fields:
            try:
                f._check_value(getattr(value, f.name))
            except (TypeError, ValueError) as e:
                raise _prefixed(e, (f.name,)) from e

    def decode(self, data) -> dict:
        return _decode_fields(self.fields, data)

    def resolve(self, data) -> dict:
        if type(data) is self.cls:
            raise SchemaTypeError(f"expected dict, got {self.cls.__name__} instance")
        return _resolve_fields(self.fields, data, kind="key")

    def build(self, data) -> object:
        return self._construct(self.resolve(data))

    def to_dict(self) -> dict:
        # Lazy import avoids the cycle with the contract emitter.
        from pytypehint.contract import _struct_document
        return _struct_document(self)

    def _construct(self, resolved, *, _path: tuple = ()) -> object:
        return self.cls(**_build_kwargs(self.fields, resolved, _path=_path))

    def _check_kwargs(self, data) -> None:
        _resolve_fields(self.fields, data, kind="key", fill=False)

    def _resolve_for_build(self, data) -> dict:
        return _resolve_fields(self.fields, data, kind="key", check_present=False)

    def __repr__(self) -> str:
        cls = getattr(self, "cls", None)
        return f"Struct({cls.__name__})" if cls is not None else "Struct(<incomplete>)"


@dataclass(frozen=True, kw_only=True, eq=False)
class Field:
    name: str
    shape: tuple
    default: object = MISSING
    label: Label | None = None
    description: Description | None = None
    optional_toggle: OptionalToggle | None = None
    _recipe: object = field(default=MISSING, init=False, repr=False, compare=False)
    _deferred: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self):
        check_opt("Field", "label", self.label, Label)
        check_opt("Field", "description", self.description, Description)

        check_opt("Field", "optional_toggle", self.optional_toggle, OptionalToggle)

        if type(self.name) is not str:
            raise TypeError(f"Field.name must be str, got {type(self.name).__name__}")

        if not self.name.isidentifier():
            raise ValueError(f"Field.name must be an identifier, got {self.name!r}")

        if type(self.shape) is not tuple or not self.shape:
            raise TypeError("Field.shape must be a non-empty tuple of shapes")

        for s in self.shape:
            if not isinstance(s, Shape):
                raise TypeError(f"Field.shape: {type(s).__name__} is not a shape")

        _check_discriminators(self.name, self.shape)

        if len(self.shape) == 1 and isinstance(self.shape[0], NoneShape):
            raise TypeError(f"Field {self.name!r}: None must be accompanied by another option")

        if self.optional_toggle is not None and not any(isinstance(s, NoneShape) for s in self.shape):
            raise TypeError(
                f"Field {self.name!r}: {type(self.optional_toggle).__name__} "
                f"requires an optional field (X | None)")

        object.__setattr__(self, "_recipe", self.default)

        if all(_ready(s) for s in self.shape):
            if duplicate_options(self.shape):
                raise ValueError(f"Field {self.name!r}: duplicate option types in shape")
            object.__setattr__(self, "default", _certify(self))
            object.__setattr__(self, "_deferred", False)
        else:
            object.__setattr__(self, "_deferred", True)

    def _check_value(self, value) -> None:
        check_options_value(self.shape, value)

    def _check_value_data(self, value) -> None:
        _data_shape(self.shape, value)


def _check_discriminators(field_name: str, shapes) -> None:
    duplicates = duplicate_discriminators(shapes)
    if duplicates:
        raise ValueError(
            f"Field {field_name!r}: duplicate discriminator name(s): "
            f"{', '.join(duplicates)}")

    for shape in shapes:
        if type(shape) is List:
            _check_discriminators(field_name, shape.item)
        elif type(shape) is Tuple:
            for options in shape.items:
                _check_discriminators(field_name, options)


def _data_type(shape) -> type:
    return dict if type(shape) is Struct else shape.pytype


def _wrapped_options(shapes) -> tuple:
    groups: dict[type, list] = {}
    for shape in shapes:
        groups.setdefault(_data_type(shape), []).append(shape)
    return tuple(shape for data_type, group in groups.items()
                 for shape in group
                 if len(group) > 1 and data_type is not dict)


def _is_wrapped(shapes, wrapped, value) -> bool:
    return bool(wrapped) and (
        _VALUE in value or not any(type(shape) is Struct for shape in shapes))


def _wrapped_shape(wrapped, value):
    names = tuple(shape.option_id() for shape in wrapped)

    if _TYPE not in value:
        joined = " | ".join(names)
        raise SchemaTypeError(
            f'ambiguous value: field accepts {joined} — wrap it as '
            f'{{"{_TYPE}": ..., "{_VALUE}": ...}} naming the option')

    discriminator = value[_TYPE]
    if type(discriminator) is not str:
        raise SchemaTypeError(
            f"expected str, got {type(discriminator).__name__}", (_TYPE,))
    if discriminator not in names:
        raise SchemaValueError(
            f"not a choice: {discriminator!r}, expected one of {names}", (_TYPE,))

    extra = sorted(str(k) for k in value if k not in (_TYPE, _VALUE))
    if extra:
        raise SchemaTypeError(f"unexpected key(s): {', '.join(extra)}")
    if _VALUE not in value:
        raise SchemaTypeError(f"missing key(s): {_VALUE}")

    shape = wrapped[names.index(discriminator)]
    try:
        _data_shape((shape,), value[_VALUE])
    except (TypeError, ValueError) as e:
        raise _prefixed(e, (_VALUE,)) from e
    return shape


def _data_shape(shapes, value):
    structs = [shape for shape in shapes if type(shape) is Struct]
    for shape in structs:
        if type(value) is shape.cls:
            raise SchemaTypeError(f"expected dict, got {shape.cls.__name__} instance")

    wrapped = _wrapped_options(shapes)

    if type(value) is dict:
        # Check key types before lookups can invoke foreign __eq__ on a hash collision.
        invalid = next((key for key in value if type(key) is not str), MISSING)
        if invalid is not MISSING:
            raise SchemaTypeError(
                f"expected string keys, got {type(invalid).__name__}")
        if _is_wrapped(shapes, wrapped, value):
            return _wrapped_shape(wrapped, value)
        if not structs:
            raise SchemaTypeError(f"expected {accepted(shapes)}, got dict")
        if len(structs) == 1:
            shape = structs[0]
            shape._check_kwargs(value)
            return shape

        names = tuple(shape.cls.__name__ for shape in structs)
        if _TYPE not in value:
            joined = " | ".join(names)
            raise SchemaTypeError(
                f'ambiguous dict: field accepts {joined} — add "{_TYPE}" naming the variant')
        discriminator = value[_TYPE]
        if type(discriminator) is not str:
            raise SchemaTypeError(
                f"expected str, got {type(discriminator).__name__}", (_TYPE,))
        if discriminator not in names:
            error = SchemaValueError(
                f"not a choice: {discriminator!r}, expected one of {names}", (_TYPE,))
            elsewhere = next(
                (shape for shape in shapes
                 if shape.discriminator != Struct.discriminator
                 and shape.option_id() == discriminator), None)
            if elsewhere is not None:
                error.add_note(
                    f"{discriminator!r} is an option of this field, but one named "
                    f'inside the "{_TYPE}"/"{_VALUE}" wrapper rather than among '
                    f"the dataclasses: the wrapper is still here because its "
                    f'"{_VALUE}" did not read as {discriminator}')
            raise error
        shape = next(shape for shape in structs if shape.cls.__name__ == discriminator)
        shape._check_kwargs({k: v for k, v in value.items() if k != _TYPE})
        return shape

    group = [shape for shape in wrapped if _data_type(shape) is type(value)]
    if group:
        joined = " | ".join(shape.option_id() for shape in group)
        raise SchemaTypeError(
            f'ambiguous {type(value).__name__}: field accepts {joined} — wrap it as '
            f'{{"{_TYPE}": ..., "{_VALUE}": ...}} naming the option')

    for shape in shapes:
        if type(value) is shape.pytype and type(shape) is not Struct:
            if type(shape) in (List, Tuple):
                shape._validate_data(value)
                for i, item in enumerate(value):
                    try:
                        _data_shape(shape._item_at(i), item)
                    except (TypeError, ValueError) as e:
                        raise _prefixed(e, (i,)) from e
            else:
                shape._check(value)
            return shape
    raise SchemaTypeError(f"expected {accepted(shapes)}, got {type(value).__name__}")


# Restrict the more permissive fromisoformat parsers to canonical ASCII text.
_DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
# Restore fractions and offsets so Time validation reports the actual violation.
_TIME_TEXT = re.compile(
    r"\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})?", re.ASCII)


def _wire_kinds(shape) -> tuple[type, ...]:
    kind = type(shape)
    if kind is Float:
        return (float, int)
    if kind in (Date, Time, EnumShape):
        return (str,)
    if kind is Struct:
        return (dict,)
    if kind is Tuple:
        return (list,)
    return (shape.pytype,)


def _portable_options(shapes) -> tuple:
    plain = [shape for shape in shapes if type(shape) is not Struct]
    counts: dict[type, int] = {}
    for shape in plain:
        for kind in _wire_kinds(shape):
            counts[kind] = counts.get(kind, 0) + 1
    return tuple(shape for shape in plain
                 if any(counts[kind] > 1 for kind in _wire_kinds(shape)))


def _plain_copy(value):
    if type(value) is dict:
        return {k: _plain_copy(v) for k, v in value.items()}
    if type(value) is list:
        return [_plain_copy(v) for v in value]
    return value


def _decode_shape(shape, value):
    kind = type(shape)

    if kind is Struct:
        return _decode_fields(shape.fields, value)

    if kind is List:
        return [_decode_options(shape.item, item) for item in value]

    if kind is Tuple:
        return tuple(_decode_options(shape._item_at(i), item)
                     for i, item in enumerate(value))

    if kind is Float:
        if type(value) is not int:
            return value
        try:
            restored = float(value)
        except OverflowError:
            return value
        return restored if restored == value else value

    if kind is Date:
        if _DATE_TEXT.fullmatch(value) is None:
            return value
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value

    if kind is Time:
        if _TIME_TEXT.fullmatch(value) is None:
            return value
        try:
            return time.fromisoformat(value)
        except ValueError:
            return value

    if kind is EnumShape:
        try:
            return shape.cls[value]
        except KeyError:
            return value

    return value


def _decode_dict(shapes, value):
    # Check key types before lookups can invoke foreign __eq__ on a hash collision.
    if any(type(key) is not str for key in value):
        return _plain_copy(value)

    portable = _portable_options(shapes)

    if _is_wrapped(shapes, portable, value):
        return _decode_wrapped(shapes, portable, value)

    structs = [shape for shape in shapes if type(shape) is Struct]
    if len(structs) == 1:
        return _decode_fields(structs[0].fields, value)
    if len(structs) > 1:
        selected = next(
            (shape for shape in structs if shape.cls.__name__ == value.get(_TYPE)), None)
        if selected is not None:
            return _decode_fields(selected.fields, value)

    return _plain_copy(value)


def _decode_wrapped(shapes, portable, value):
    if set(value) != {_TYPE, _VALUE}:
        return _plain_copy(value)

    discriminator = value[_TYPE]
    if type(discriminator) is not str:
        return _plain_copy(value)

    selected = next(
        (shape for shape in portable if shape.option_id() == discriminator), None)
    if selected is None:
        return _plain_copy(value)

    payload = _decode_options((selected,), value[_VALUE])

    # Keep failed named payloads wrapped so they cannot fall into a sibling option.
    if type(payload) is not _data_type(selected):
        return _plain_copy(value)

    if any(shape is selected for shape in _wrapped_options(shapes)):
        return {_TYPE: discriminator, _VALUE: payload}
    return payload


def _decode_options(shapes, value):
    if type(value) is dict:
        return _decode_dict(shapes, value)

    candidates = [shape for shape in shapes if type(value) in _wire_kinds(shape)]
    if len(candidates) != 1:
        return _plain_copy(value)
    return _decode_shape(candidates[0], value)


def _decode_fields(fields, data) -> dict:
    if type(data) is not dict:
        return _plain_copy(data)

    known = {f.name: f for f in fields}
    decoded = {}
    for key, value in data.items():
        f = known.get(key) if type(key) is str else None
        decoded[key] = _plain_copy(value) if f is None else _decode_options(f.shape, value)
    return decoded


# Build disables present-value checks after the outer resolve validated them.
def _resolve_fields(fields, data, *, kind: str, fill: bool = True,
                    check_present: bool = True) -> dict:
    if type(data) is not dict:
        raise SchemaTypeError(f"expected dict, got {type(data).__name__}")

    invalid_key = next((key for key in data if type(key) is not str), MISSING)
    if invalid_key is not MISSING:
        raise SchemaTypeError(
            f"expected string keys, got {type(invalid_key).__name__}")

    known = {f.name for f in fields}
    extra = sorted(k for k in data if k not in known)
    if extra:
        raise SchemaTypeError(f"unexpected {kind}(s): {', '.join(extra)}")

    missing = sorted(f.name for f in fields if f.name not in data and f.default is MISSING)
    if missing:
        raise SchemaTypeError(f"missing {kind}(s): {', '.join(missing)}")

    result = {}
    for f in fields:
        if f.name not in data:
            if fill:
                try:
                    served = _remat(f)
                    f._check_value(served)
                except (TypeError, ValueError) as e:
                    raise _prefixed(e, (f.name, "default")) from e
                except Exception as e:
                    raise _renote(
                        SchemaValueError(str(e), (f.name, "default")), e) from e
                result[f.name] = served
            continue
        if check_present:
            try:
                f._check_value_data(data[f.name])
            except (TypeError, ValueError) as e:
                raise _prefixed(e, (f.name,)) from e
        if fill:
            result[f.name] = data[f.name]
    return result


def _ready(shape) -> bool:
    if type(shape) is tuple:
        return all(_ready(item) for item in shape)
    if type(shape) is Struct:
        return hasattr(shape, "fields")
    if type(shape) is List:
        return all(_ready(item) for item in shape.item)
    if type(shape) is Tuple:
        return _ready(shape.items)
    return True


def _remat_shape(shape, value):
    if type(shape) is List:
        return [_remat_options(shape.item, v) for v in value]
    if type(shape) is Tuple:
        return tuple(_remat_options(shape._item_at(i), v) for i, v in enumerate(value))
    if type(shape) is Struct:
        return shape.cls(**{f.name: _remat_options(f.shape, getattr(value, f.name))
                            for f in shape.fields})
    return value


def _remat_options(shapes, value):
    shape = value_branch(shapes, value)
    return value if shape is None else _remat_shape(shape, value)


def _remat(field):
    recipe = field._recipe
    if type(recipe) is _Factory:
        return recipe.fn()
    return _remat_options(field.shape, recipe)


def _build_value(shape, value, path):
    if type(shape) is Struct and type(value) is dict:
        try:
            payload = {k: v for k, v in value.items() if k != _TYPE}
            resolved = shape._resolve_for_build(payload)
        except (TypeError, ValueError) as e:
            raise _prefixed(e, path) from e
        return shape._construct(resolved, _path=path)
    if type(shape) is List and type(value) is list:
        return [_build_options(shape.item, v, (*path, i))
                for i, v in enumerate(value)]
    if type(shape) is Tuple and type(value) is tuple:
        return tuple(_build_options(shape._item_at(i), v, (*path, i))
                     for i, v in enumerate(value))
    return value


def _route_dict(shapes, value):
    structs = [shape for shape in shapes if type(shape) is Struct]
    if len(structs) == 1:
        return structs[0]
    shape = next((s for s in structs if s.cls.__name__ == value.get(_TYPE)), None)
    if shape is None:
        raise AssertionError("validated dict matches no struct option")
    return shape


def _build_options(shapes, value, path):
    if any(type(shape) is Struct and type(value) is shape.cls for shape in shapes):
        return value
    wrapped = _wrapped_options(shapes)
    if type(value) is dict:
        if _is_wrapped(shapes, wrapped, value):
            shape = next((s for s in wrapped if s.option_id() == value.get(_TYPE)), None)
            if shape is None:
                raise AssertionError("validated wrapper matches no shape option")
            return _build_value(shape, value[_VALUE], (*path, _VALUE))
        shape = _route_dict(shapes, value)
    else:
        shape = value_branch(shapes, value)
        if shape is None:
            raise AssertionError("validated value matches no shape option")
    return _build_value(shape, value, path)


def _build_kwargs(fields, kwargs, *, _path: tuple = ()) -> dict:
    walked = {}
    for f in fields:
        value = kwargs[f.name]
        walked[f.name] = _build_options(f.shape, value, (*_path, f.name))
    return walked


def _certify(field):
    if field._recipe is MISSING:
        return MISSING
    try:
        product = _remat(field)
    except Exception as e:
        raise _renote(TypeError(
            f"Field {field.name!r}: default could not be materialized: {e}"), e) from e
    try:
        field._check_value(product)
    except (SchemaTypeError, SchemaValueError) as e:
        raise _renote(type(e)(e.leaf, (field.name, "default", *e.path)), e) from e
    except (TypeError, ValueError) as e:
        raise _renote(type(e)(f"Field {field.name!r}: default {e}"), e) from e
    return product
