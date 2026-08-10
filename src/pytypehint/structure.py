import re
from dataclasses import dataclass, field
from datetime import date, time
from typing import ClassVar

from pytypehint.atoms import Label, Description, OptionalToggle
from pytypehint.errors import SchemaTypeError, SchemaValueError, _prefixed, _renote
from pytypehint.shapes import (
    Date, EnumShape, Float, List, NoneShape, Shape, Time,
    duplicate_discriminators, duplicate_options,
)
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

    # A dataclass names itself inline among the other dataclasses of its slot,
    # so its identity competes only with theirs.
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
        # The emitter reads this module — the format is a separate concern with
        # its own file, and the schema is what it describes — so importing it at
        # module level here would close the loop. `Signature` has no such
        # problem and imports it normally.
        from pytypehint.contract import _struct_document
        return _struct_document(self)

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


# Two options indistinguishable by option_id() — their public identity — are a
# The field's side of `shapes.duplicate_discriminators`, which is where the rule
# and the reasoning behind it live. All this adds is the name of the slot being
# refused.
def _check_discriminators(field_name: str, shapes) -> None:
    duplicates = duplicate_discriminators(shapes)
    if duplicates:
        raise ValueError(
            f"Field {field_name!r}: duplicate discriminator name(s): "
            f"{', '.join(duplicates)}")

    # A `List` applies the rule to its own items, so no list holding a collision
    # can be built to reach this. Kept as a second pass because it costs two
    # lines and reports at the field's coordinates rather than the list's.
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
        # Every dict is typed before anything asks it a question. Below this
        # line the routing probes reserved keys — `"$value" in value` for a
        # wrapper, `_TYPE not in value` for a dataclass namespace, the field
        # names for a struct — and each probe runs a non-string key's own
        # `__eq__` on a hash collision: arbitrary code, which may raise anything,
        # on a path that owes its caller a schema error and nothing else. The
        # guard used to sit under `if wrapped:`, which left the dataclass branch
        # asking the question it was written to prevent. `_decode_dict` declines
        # it in the same way, and for the same reason.
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
            # The name may be a real identity of this very field, living in the
            # other namespace: a portable wrapper that `decode` declined to
            # consume because its payload never read as the option it named, and
            # that therefore arrived here still a dict, among the dataclasses.
            # Offering only the dataclass names reads as denying an identity the
            # document publishes, so the note says where the name does belong.
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


# ---------------------------------------------------------------------------
# Portable representation
#
# A portable tree is built from the types a JSON document can carry: dict, list,
# str, int, float, bool and None. Three of the core's types have no such carrier
# and arrive spelled as something else — a date and a time as text, an enum
# member as the name of that member — and a float that happens to be whole may
# arrive as an int, because that is what a JSON writer emits for it.
#
# `decode` restores those, and does nothing else. It never reads a value to
# decide which option of a union it is: the schema decides the reading, and where
# the schema alone cannot, the value is returned untouched so that validation
# reports it. That is the whole difference between this and coercion — decode
# recovers a representation the transport lost, it does not reinterpret a value
# the author wrote. See docs/decode.md.
# ---------------------------------------------------------------------------

# The canonical spellings, matched exactly. `date.fromisoformat` and
# `time.fromisoformat` accept far more than these and their grammars overlap:
# "20200101" reads as a date *and* as a time, and "2020" reads as 20:20. Letting
# them decide would make the text of a value select an option, which is the one
# thing this module must never do, so the accepted forms are pinned here instead.
# The two are disjoint: character three is "-" in one and ":" in the other, and
# neither pattern admits the other's. That is a property of the spellings and not
# what keeps a `date | time` slot safe — every `str` is a candidate for both
# shapes as far as `_wire_kinds` is concerned, and `_decode_options` declines on
# the count of candidates before any pattern is consulted. ASCII, because `\d`
# otherwise admits every decimal digit Unicode defines and the spelling would be
# canonical only as far as the parser behind it agrees.
_DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
# Seconds are optional because a wire producer may omit them. A fractional part
# and an offset are admitted although `Time` accepts neither: they are spellings
# of a time, so reading them lets the shape report its own rule — "time precision
# is limited to whole seconds", "must be naive" — instead of the value falling
# through as "not a time at all".
_TIME_TEXT = re.compile(
    r"\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})?", re.ASCII)


# The portable types a shape can arrive as. `int` is listed for `Float` because a
# whole float loses its fraction on the way out; every other shape has exactly one.
def _wire_kinds(shape) -> tuple[type, ...]:
    kind = type(shape)
    if kind is Float:
        return (float, int)
    if kind in (Date, Time, EnumShape):
        return (str,)
    if kind is Struct:
        return (dict,)
    return (shape.pytype,)


# Options whose portable spellings collide, so the value alone cannot name one.
# Structs are excluded: they arrive as dicts and are told apart by an inline
# "$type", which also keeps a dataclass and an enum of the same class name from
# competing for a single discriminator.
def _portable_options(shapes) -> tuple:
    plain = [shape for shape in shapes if type(shape) is not Struct]
    counts: dict[type, int] = {}
    for shape in plain:
        for kind in _wire_kinds(shape):
            counts[kind] = counts.get(kind, 0) + 1
    return tuple(shape for shape in plain
                 if any(counts[kind] > 1 for kind in _wire_kinds(shape)))


# Everything decode returns is freshly built, so the caller's tree is never
# touched and the result is never wired back into it. A subtree decode cannot
# route is copied rather than shared, for the same reason.
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

    if kind is Float:
        if type(value) is not int:
            return value
        try:
            restored = float(value)
        except OverflowError:
            # An integer too large to be a float is not a float written without
            # its fraction; there is nothing to restore, so it is handed back.
            return value
        # Nor is an integer that no float equals, which is the same fact one step
        # earlier: above 2**53 the floats thin out, so `float(2**53 + 1)` answers
        # with a neighbour instead of failing. Restoring that would hand `build` a
        # number the transport never carried, and `build` would accept it — the
        # one payload decode must not invent. The test is exactness, not size.
        return restored if restored == value else value

    if kind is Date:
        if _DATE_TEXT.fullmatch(value) is None:
            return value
        try:
            return date.fromisoformat(value)
        except ValueError:
            # The spelling is canonical but the date is not real (2026-02-31).
            # Validation names that better than decode could.
            return value

    if kind is Time:
        if _TIME_TEXT.fullmatch(value) is None:
            return value
        try:
            return time.fromisoformat(value)
        except ValueError:
            return value

    if kind is EnumShape:
        # By member name, never by member value: a name is always a string and
        # always identifies one member, while a value may be unrepresentable in
        # a portable tree and may read as another member's name. `__members__`
        # is consulted through the class, so an alias resolves to the member it
        # aliases — the same object the schema validates against.
        try:
            return shape.cls[value]
        except KeyError:
            return value

    return value


# A dict is either a dataclass payload or a discriminated wrapper. `_is_wrapped`
# already tells the two apart for validation, and the same answer is used here.
def _decode_dict(shapes, value):
    # Every key of a portable tree is a string, and the reserved keys and field
    # names are looked up by hashing against these. A key that is not a string
    # cannot match any of them, and asking whether it does would run its own
    # `__eq__` on a hash collision — arbitrary code, possibly raising, on a path
    # that has to be total. So a dict carrying one is not routed at all, and
    # validation reports the keys.
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
    # Anything that is not exactly the two reserved keys is not a wrapper, and
    # decode does not diagnose it: it hands the dict back for validation to
    # report, with the coordinates and wording that already exist for it.
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

    # The wrapper only names an option; it is not itself data. Consuming one
    # whose payload did not reach the named option would file the value under a
    # different option in silence — a date that failed to parse would settle as
    # the `str` beside it. So the wrapper survives, and validation reports it.
    if type(payload) is not _data_type(selected):
        return _plain_copy(value)

    # Where the options also share a Python type, validation still needs the
    # discriminator to route them, so the wrapper is kept and only its payload
    # is decoded. Everywhere else the exact value is enough on its own and the
    # wrapper has done its work.
    if any(shape is selected for shape in _wrapped_options(shapes)):
        return {_TYPE: discriminator, _VALUE: payload}
    return payload


def _decode_options(shapes, value):
    if type(value) is dict:
        return _decode_dict(shapes, value)

    candidates = [shape for shape in shapes if type(value) in _wire_kinds(shape)]
    if len(candidates) != 1:
        # No option reads this spelling, or more than one does. Either way the
        # reading is not the schema's to make, so the value stands as it came.
        return _plain_copy(value)
    return _decode_shape(candidates[0], value)


# The third field-list operation, beside `_resolve_fields` and `_build_kwargs`.
# Unknown keys travel through untouched and absent keys stay absent: naming them
# is `resolve`'s work, and filling them is the defaults'.
def _decode_fields(fields, data) -> dict:
    if type(data) is not dict:
        return _plain_copy(data)

    known = {f.name: f for f in fields}
    decoded = {}
    for key, value in data.items():
        # Only a string can name a field, and only a string is asked to. See
        # `_decode_dict` on why the question is not put to anything else.
        f = known.get(key) if type(key) is str else None
        decoded[key] = _plain_copy(value) if f is None else _decode_options(f.shape, value)
    return decoded


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


# _data_shape both validates a dict and reports the option it selected, but the
# selection is not handed on: the outer resolve ran it for validation, and
# construction re-derives it from the same rules and asserts that it agrees. The
# assertions are the seam — they hold while both readings of "which option is
# this" stay one rule, and they are what would fail first if they stopped.
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
        raise _renote(TypeError(
            f"Field {field.name!r}: default could not be materialized: {e}"), e) from e
    try:
        field._check_value(product)
    except (SchemaTypeError, SchemaValueError) as e:
        # Compile-time certification keeps the structured guarantee: the field
        # name and "default" travel in the path as clean coordinates, the
        # violation stays the leaf. The render matches the runtime serving path
        # (`_resolve_fields`) exactly — one format for one concept.
        raise _renote(type(e)(e.leaf, (field.name, "default", *e.path)), e) from e
    except (TypeError, ValueError) as e:
        # A foreign TypeError/ValueError carries no structure to preserve —
        # except its notes, which are the detail it was raised to carry.
        raise _renote(type(e)(f"Field {field.name!r}: default {e}"), e) from e
    return product
