from dataclasses import dataclass, field

from pytypehint.atoms import Label, Description, OptionalToggle
from pytypehint.errors import SchemaTypeError, SchemaValueError, _prefixed
from pytypehint.shapes import NoneShape, List, Shape, duplicate_options
from pytypehint.utils import MISSING, check_opt
from pytypehint.validation import accepted, check_options_value, value_branch

# Reserved keys of the discriminated wrapper. Neither can collide with a
# dataclass field: field names must be identifiers.
_TYPE = "$type"
_VALUE = "$value"


# A factory remains callable so each missing key receives a fresh product.
@dataclass(frozen=True)
class _Factory:
    fn: object


@dataclass(frozen=True, kw_only=True, eq=False)
class Struct(Shape):
    cls: type
    # String form avoids the forward reference to Field.
    fields: "tuple[Field, ...]"

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

    def resolve(self, data) -> dict:
        if type(data) is self.cls:
            raise SchemaTypeError(f"expected dict, got {self.cls.__name__} instance")
        return _resolve_fields(self.fields, data, kind="key")

    def build(self, data) -> object:
        return self._construct(self.resolve(data))

    def _construct(self, resolved, *, _path: tuple = ()) -> object:
        return self.cls(**_build_kwargs(self.fields, resolved, _path=_path))

    def _check_kwargs(self, data) -> None:
        _resolve_fields(self.fields, data, kind="key", fill=False)

    # Present keys arrived validated from the outer resolve; this fills and
    # validates the absent ones at their own depth.
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
    # Set by __post_init__: the recipe behind `default`, and whether a recursive
    # shape graph postponed its certification.
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

        # _recipe serves fresh values; default exposes its certified product.
        # Recursive shapes defer certification until their graph is complete.
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
    structs = [shape for shape in shapes if type(shape) is Struct]
    by_name: dict[str, set[type]] = {}
    for shape in structs:
        by_name.setdefault(shape.cls.__name__, set()).add(shape.cls)
    duplicates = sorted(name for name, classes in by_name.items()
                        if len(classes) > 1)
    if duplicates:
        raise ValueError(
            f"Field {field_name!r}: duplicate discriminator name(s): "
            f"{', '.join(duplicates)}")

    for shape in shapes:
        if type(shape) is List:
            _check_discriminators(field_name, shape.item)


# Input data routes by the runtime type it arrives as, and every dataclass
# arrives as a dict.
def _data_type(shape) -> type:
    return dict if type(shape) is Struct else shape.pytype


# Options that share one input type and are not dataclasses. Dataclasses are
# left out: several of them are also unroutable, but a dict has room for an
# inline "$type" and keeps the format it has always had. Everything else needs
# the value moved into a wrapper to make room for the discriminator.
def _wrapped_options(shapes) -> tuple:
    groups: dict[type, list] = {}
    for shape in shapes:
        groups.setdefault(_data_type(shape), []).append(shape)
    return tuple(shape for data_type, group in groups.items()
                 for shape in group
                 if len(group) > 1 and data_type is not dict)


# A wrapper is a dict, and so is a dataclass payload. "$value" separates them:
# it is reserved, and a dataclass can never carry it. Without dataclass options
# every dict is a wrapper attempt, so a missing "$type" reports as one.
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
    # The discriminator is a coordinate of its own, so it travels in the path.
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

    # The discriminator selected one option; the payload is validated against
    # that option alone, one level deeper.
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
            raise SchemaValueError(
                f"not a choice: {discriminator!r}, expected one of {names}", (_TYPE,))
        shape = next(shape for shape in structs if shape.cls.__name__ == discriminator)
        shape._check_kwargs({k: v for k, v in value.items() if k != _TYPE})
        return shape

    # A bare value whose type is shared by several options carries no evidence
    # of which one it is, and the core does not read its contents to invent any.
    group = [shape for shape in wrapped if _data_type(shape) is type(value)]
    if group:
        joined = " | ".join(shape.option_id() for shape in group)
        raise SchemaTypeError(
            f'ambiguous {type(value).__name__}: field accepts {joined} — wrap it as '
            f'{{"{_TYPE}": ..., "{_VALUE}": ...}} naming the option')

    for shape in shapes:
        if type(value) is shape.pytype and type(shape) is not Struct:
            if type(shape) is List:
                shape._validate_data(value)
                for i, item in enumerate(value):
                    try:
                        _data_shape(shape.item, item)
                    except (TypeError, ValueError) as e:
                        raise _prefixed(e, (i,)) from e
            else:
                shape._check(value)
            return shape
    raise SchemaTypeError(f"expected {accepted(shapes)}, got {type(value).__name__}")


# check_present=False is used only by the build path, whose outer resolve already
# validated the present keys; the absent ones are still filled and validated.
# See docs/build.md.
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
                # Every serving is validated; impure recipes fail on a `default` path.
                try:
                    served = _remat(f)
                    f._check_value(served)
                except (TypeError, ValueError) as e:
                    raise _prefixed(e, (f.name, "default")) from e
                except Exception as e:
                    raise SchemaValueError(str(e), (f.name, "default")) from e
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


# Container shapes descend into their children so defaults are not certified
# against incomplete recursive Structs.
def _ready(shape) -> bool:
    if type(shape) is tuple:
        return all(_ready(item) for item in shape)
    if type(shape) is Struct:
        return hasattr(shape, "fields")
    if type(shape) is List:
        return all(_ready(item) for item in shape.item)
    return True


# Recipes run for certification and for each missing-key serving.
def _remat_shape(shape, value):
    if type(shape) is List:
        return [_remat_options(shape.item, v) for v in value]
    if type(shape) is Struct:
        # Instance recipes reconstruct through the user's constructor.
        return shape.cls(**{f.name: _remat_options(f.shape, getattr(value, f.name))
                            for f in shape.fields})
    # Immutable scalars and enum singletons pass as is.
    return value


def _remat_options(shapes, value):
    shape = value_branch(shapes, value)
    # Certification reports the exact type error for unmatched defaults.
    return value if shape is None else _remat_shape(shape, value)


def _remat(field):
    recipe = field._recipe
    if type(recipe) is _Factory:
        return recipe.fn()
    return _remat_options(field.shape, recipe)


# Nested construction for build: turn a validated kwargs dict into constructor
# arguments — a dict resolves its defaults and becomes an instance at its own
# depth, and a list is rebuilt fresh with its contents constructed.
def _build_value(shape, value, path):
    if type(shape) is Struct and type(value) is dict:
        # The present keys were validated once, by the outer resolve. Mutating the
        # input dict during construction is undefined behaviour and the author's
        # responsibility, exactly like default purity: nothing here watches for it.
        try:
            payload = {k: v for k, v in value.items() if k != _TYPE}
            resolved = shape._resolve_for_build(payload)
        except (TypeError, ValueError) as e:
            raise _prefixed(e, path) from e
        return shape._construct(resolved, _path=path)
    if type(shape) is List and type(value) is list:
        return [_build_options(shape.item, v, (*path, i))
                for i, v in enumerate(value)]
    return value


# _data_shape both validates a dict and reports the option it selected. The outer
# resolve already ran it for validation, so construction needs the selection only.
def _route_dict(shapes, value):
    structs = [shape for shape in shapes if type(shape) is Struct]
    if len(structs) == 1:
        return structs[0]
    shape = next((s for s in structs if s.cls.__name__ == value.get(_TYPE)), None)
    if shape is None:
        raise AssertionError("validated dict matches no struct option")
    return shape


def _build_options(shapes, value, path):
    # Rematerialized instance defaults have already passed schema validation.
    if any(type(shape) is Struct and type(value) is shape.cls for shape in shapes):
        return value
    wrapped = _wrapped_options(shapes)
    if type(value) is dict:
        if _is_wrapped(shapes, wrapped, value):
            # The wrapper is packaging, not data: only its payload is built.
            shape = next((s for s in wrapped if s.option_id() == value.get(_TYPE)), None)
            if shape is None:
                raise AssertionError("validated wrapper matches no shape option")
            return _build_value(shape, value[_VALUE], (*path, _VALUE))
        shape = _route_dict(shapes, value)
    else:
        # A filled default arrives as a value, not as wrapped data.
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
        raise TypeError(
            f"Field {field.name!r}: default could not be materialized: {e}") from e
    try:
        field._check_value(product)
    except (TypeError, ValueError) as e:
        raise type(e)(f"Field {field.name!r}: default {e}") from e
    return product
