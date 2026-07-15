from dataclasses import dataclass, field

from pytypehint.atoms import Label, Description, OptionalToggle
from pytypehint.errors import SchemaTypeError, SchemaValueError, _prefixed
from pytypehint.shapes import NoneShape, List, Shape
from pytypehint.utils import MISSING, check_opt
from pytypehint.validation import check_options_value


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
            pytypes = [s.pytype for s in self.shape]
            if len(pytypes) != len(set(pytypes)):
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


def _accepted(shapes) -> str:
    return " | ".join(s.pytype.__name__ for s in shapes)


def _data_shape(shapes, value):
    structs = [shape for shape in shapes if type(shape) is Struct]
    for shape in structs:
        if type(value) is shape.cls:
            raise SchemaTypeError(f"expected dict, got {shape.cls.__name__} instance")

    if type(value) is dict:
        if not structs:
            raise SchemaTypeError(f"expected {_accepted(shapes)}, got dict")
        if len(structs) == 1:
            shape = structs[0]
            shape._check_kwargs(value)
            return shape

        names = tuple(shape.cls.__name__ for shape in structs)
        if "$type" not in value:
            joined = " | ".join(names)
            raise SchemaTypeError(
                f'ambiguous dict: field accepts {joined} — add "$type" naming the variant')
        discriminator = value["$type"]
        # The discriminator is a coordinate of its own, so it travels in the path.
        if type(discriminator) is not str:
            raise SchemaTypeError(
                f"expected str, got {type(discriminator).__name__}", ("$type",))
        if discriminator not in names:
            raise SchemaValueError(
                f"not a choice: {discriminator!r}, expected one of {names}", ("$type",))
        shape = next(shape for shape in structs if shape.cls.__name__ == discriminator)
        shape._check_kwargs({k: v for k, v in value.items() if k != "$type"})
        return shape

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
    raise SchemaTypeError(f"expected {_accepted(shapes)}, got {type(value).__name__}")


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
    for s in shapes:
        if type(value) is s.pytype:
            return _remat_shape(s, value)
    # Certification reports the exact type error for unmatched defaults.
    return value


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
            payload = {k: v for k, v in value.items() if k != "$type"}
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
    shape = next((s for s in structs if s.cls.__name__ == value.get("$type")), None)
    if shape is None:
        raise AssertionError("validated dict matches no struct option")
    return shape


def _build_options(shapes, value, path):
    # Rematerialized instance defaults have already passed schema validation.
    if any(type(shape) is Struct and type(value) is shape.cls for shape in shapes):
        return value
    if type(value) is dict:
        shape = _route_dict(shapes, value)
    else:
        shape = next((shape for shape in shapes if type(value) is shape.pytype), None)
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
