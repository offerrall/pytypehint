import inspect
import types
from dataclasses import (
    MISSING as _DC_MISSING, Field as _DcField, InitVar as _InitVar,
    fields as dc_fields, is_dataclass,
)
from enum import Enum
from typing import Annotated, Literal, Union, get_args, get_origin, get_type_hints

from pytypehint import atoms
from pytypehint.atoms import Choices, Description, Extra, Label, OptionalToggle
from pytypehint.shapes import (
    Bool, Date, EnumShape, Float, Int, List, NoneShape, Shape, Str, Time,
    duplicate_options,
)
from pytypehint.signature import Signature
from pytypehint.structure import Field, Struct, _Factory, _certify
from pytypehint.utils import MISSING

_ATOM_CLASSES = {v for v in vars(atoms).values()
                 if isinstance(v, type) and is_dataclass(v)
                 and v.__module__ == atoms.__name__}
_FIELD_ATOMS = (Label, Description, OptionalToggle)


def _atom_type(hint):
    if get_origin(hint) in (Union, types.UnionType):
        hint = next((a for a in get_args(hint) if a is not type(None)), None)
    return hint if hint in _ATOM_CLASSES else None


def _atoms_of(shape_cls):
    hints = get_type_hints(shape_cls)
    table = {a: f.name for f in dc_fields(shape_cls)
             if (a := _atom_type(hints[f.name])) is not None}

    # Extras merge into one field of key/value pairs, so no field is hinted
    # `Extra | None` for the reflection above to find. The table still decides
    # acceptance: shapes without the field keep rejecting Extra as unsupported.
    if any(f.name == "_extras" for f in dc_fields(shape_cls)):
        table[Extra] = "_extras"

    return table


_VOCABULARY = {cls.pytype: (cls, _atoms_of(cls))
               for cls in (Int, Float, Bool, Str, Date, Time,
                           NoneShape, List)}


def _kwargs_of(meta, kind, table):
    kwargs = {}
    extras: dict[str, str] = {}
    for m in meta:
        name = table.get(type(m))
        if name is None:
            raise TypeError(f"unsupported metadata for {kind}: {m!r}")

        # Extras layer per key, not per atom class: different keys accumulate,
        # a repeated key is overwritten. Typing flattens Annotated before we see
        # it, so the rightmost atom is the outer layer and the standard rule
        # falls out of writing the key in order.
        if type(m) is Extra:
            extras[m.key] = m.value
            continue

        kwargs[name] = m

    if extras:
        kwargs[table[Extra]] = tuple(sorted(extras.items()))

    return kwargs


def _split_annotated(hint):
    if get_origin(hint) is Annotated:
        base, *meta = get_args(hint)
        return base, tuple(meta)
    return hint, ()


def _options_of(hint):
    if get_origin(hint) in (Union, types.UnionType):
        return get_args(hint)
    return (hint,)


def _hint_label(hint) -> str:
    return hint.__name__ if isinstance(hint, type) else str(hint).replace("typing.", "")


# Two hints can read as different options and still compile to one shape:
# Literal['a'] and str both become Str. Sharing a runtime type is not enough to
# collide — list[str] and list[int] do, and a discriminator tells them apart —
# but sharing the identity that discriminator would use leaves nothing to name.
# List.item reports the collision by shape, which cannot name the hints the
# author actually wrote — this can.
def _reject_colliding_items(raw_options, item_options) -> None:
    seen: dict[tuple[type, str], object] = {}
    for hint, shape in zip(raw_options, item_options):
        key = (shape.pytype, shape.option_id())
        if key in seen:
            raise ValueError(
                f"list items: {_hint_label(seen[key])} and {_hint_label(hint)} "
                f"both compile to {shape.option_id()} — merge them into one option, "
                f"or give each variant a dataclass and route with $type")
        seen[key] = hint


def _shape_of(opt, cache: dict) -> Shape:
    base, meta = _split_annotated(opt)

    if base is None:
        base = type(None)

    if base is list:
        raise TypeError("list requires an item type: list[X]")

    if get_origin(base) is list:
        (item_hint,) = get_args(base)
        item_base, item_meta = _split_annotated(item_hint)
        if any(isinstance(m, _FIELD_ATOMS) for m in item_meta):
            raise TypeError("field atoms cannot apply to list items")
        raw_options = _options_of(item_base)
        if len(raw_options) > 1 and item_meta:
            raise TypeError(
                "metadata on a union of multiple types must go per option: "
                "Annotated[int, Min(0)] | str")
        item_options = ((_shape_of(item_hint, cache),) if len(raw_options) == 1
                        else tuple(_shape_of(o, cache) for o in raw_options))
        if len(raw_options) > 1:
            _reject_colliding_items(raw_options, item_options)
        return List(item=item_options,
                    **_kwargs_of(meta, "list", _VOCABULARY[list][1]))

    if get_origin(base) is Literal:
        values = get_args(base)
        for v in values:
            if type(v) is float:
                raise TypeError("Literal values must be int or str, got float — "
                                "for float choices use Annotated[float, Choices(...)]")
            if type(v) not in (int, str):
                raise TypeError(f"Literal values must be int or str, got {type(v).__name__}")
        if len({type(v) for v in values}) > 1:
            raise TypeError("Literal values must all be the same type")
        if any(type(m) is Choices for m in meta):
            raise TypeError("Literal already defines its choices")
        return _shape_of(Annotated[tuple([type(values[0]),
                                          Choices(values=values), *meta])], cache)

    if base in _VOCABULARY:
        shape_cls, table = _VOCABULARY[base]
        return shape_cls(**_kwargs_of(meta, base.__name__, table))

    if isinstance(base, type) and issubclass(base, Enum):
        _kwargs_of(meta, "enum", {})
        return EnumShape(cls=base)

    if isinstance(base, type) and is_dataclass(base):
        _kwargs_of(meta, "dataclass", {})
        return _struct_of_class(base, cache)

    raise TypeError(f"unsupported type: {base!r}")


def _field_atoms_of(meta):
    field_atoms = {}
    type_meta = []
    for m in meta:
        if isinstance(m, _FIELD_ATOMS):
            field_atoms[type(m)] = m
        else:
            type_meta.append(m)
    return field_atoms, type_meta


def _field_of(name: str, hint, default, cache: dict) -> Field:
    base_hint, meta = _split_annotated(hint)

    outer_atoms, type_meta = _field_atoms_of(meta)

    options = _options_of(base_hint)

    if type_meta:
        # None expresses optionality; type metadata targets the single real option.
        real_opts = [o for o in options if o is not type(None) and o is not None]
        if len(real_opts) == 0:
            raise TypeError(f"{name}: metadata on None: None is optionality, not a type")
        if len(real_opts) > 1:
            raise TypeError(
                f"{name}: metadata on a union of multiple types must go per option: "
                f"Annotated[int, Min(0)] | str")
        # Preserve the user's union-option order.
        options = tuple(
            Annotated[tuple([o, *type_meta])]
            if o is not type(None) and o is not None else o
            for o in options)

    # typing flattens Annotated aliases; hoist their field atoms before compiling.
    hoisted: dict[type, object] = {}
    stripped = []
    for opt in options:
        opt_base, opt_meta = _split_annotated(opt)
        opt_atoms, opt_type_meta = _field_atoms_of(opt_meta)
        for atom_type, atom in opt_atoms.items():
            if atom_type in outer_atoms:
                continue
            existing = hoisted.get(atom_type)
            if existing is not None and existing != atom:
                raise TypeError(
                    f"{name}: conflicting {atom_type.__name__.lower()}s across union options: "
                    f"{getattr(existing, 'value', existing)!r} vs {getattr(atom, 'value', atom)!r}")
            hoisted[atom_type] = atom
        stripped.append(
            Annotated[tuple([opt_base, *opt_type_meta])] if opt_type_meta else opt_base)

    field_atoms = {**hoisted, **outer_atoms}

    return Field(name=name, shape=tuple(_shape_of(o, cache) for o in stripped),
                 default=default,
                 label=field_atoms.get(Label),
                 description=field_atoms.get(Description),
                 optional_toggle=field_atoms.get(OptionalToggle))


def _default_of(f):
    if f.default is not _DC_MISSING:
        return f.default
    if f.default_factory is not _DC_MISSING:
        # The factory is the recipe and runs for each missing-key serving.
        return _Factory(f.default_factory)
    return MISSING


def _struct_of_class(cls: type, cache: dict) -> Struct:
    if cls in cache:
        return cache[cls]

    struct = Struct.__new__(Struct)
    cache[cls] = struct
    object.__setattr__(struct, "cls", cls)

    hints = get_type_hints(cls, include_extras=True)

    # InitVar enters construction but is absent from the instance, so no Field can represent it.
    # The resolved hint carries that fact itself; ClassVar resolves to ClassVar, not InitVar.
    initvars = sorted(n for n, h in hints.items() if isinstance(h, _InitVar))
    if initvars:
        raise TypeError(f"{initvars[0]}: InitVar fields are not supported")

    flds = []
    for f in dc_fields(cls):
        if not f.init:
            raise TypeError(f"{f.name}: init=False fields are not supported")
        raw = _default_of(f)
        fld = _field_of(f.name, hints[f.name], raw, cache)
        flds.append(fld)

    object.__setattr__(struct, "fields", tuple(flds))
    struct.__post_init__()

    return struct


def _validate_cache(cache: dict) -> None:
    # Recursive fields certify after the complete shape graph exists.
    for struct in cache.values():
        for f in struct.fields:
            if not f._deferred:
                continue
            if duplicate_options(f.shape):
                raise ValueError(f"Field {f.name!r}: duplicate option types in shape")
            object.__setattr__(f, "default", _certify(f))
            object.__setattr__(f, "_deferred", False)


def struct_of(obj) -> Struct:
    if is_dataclass(obj):
        if not isinstance(obj, type):
            raise TypeError(f"expected a dataclass type, got an instance of {type(obj).__name__}")
        cache: dict[type, Struct] = {}
        root = _struct_of_class(obj, cache)
        _validate_cache(cache)
        return root

    if isinstance(obj, type):
        raise TypeError(
            f"{obj.__name__} is not a dataclass — add @dataclass; "
            f"pytypehint reads standard dataclasses, it doesn't replace them")

    raise TypeError(f"expected a dataclass type, got {obj!r}")


def signature_of(fn) -> Signature:
    if not inspect.isfunction(fn):
        raise TypeError(
            f"expected a plain function, got {fn!r} — bound methods, partials and "
            f"callable objects are not supported: wrap the call in a plain function "
            f"(def run(q: str): return service.search(q))")

    if fn.__name__ == "<lambda>":
        raise TypeError("lambdas have no usable name; use a named function")

    hints = get_type_hints(fn, include_extras=True)
    cache: dict[type, Struct] = {}
    params = []

    for i, (n, p) in enumerate(inspect.signature(fn).parameters.items()):
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(f"{n}: variadic parameters (*args/**kwargs) are not supported")

        if p.kind is inspect.Parameter.POSITIONAL_ONLY:
            raise TypeError(f"{n}: positional-only parameters are not supported")

        # An unhinted leading self/cls identifies an unbound method.
        if i == 0 and n in ("self", "cls") and n not in hints:
            raise TypeError(
                f"{n}: looks like an unbound method — pytypehint takes "
                f"plain functions; wrap the call (def run(q: str): return "
                f"service.search(q))")

        if n not in hints:
            raise TypeError(f"{n}: missing type hint")

        default = MISSING if p.default is inspect.Parameter.empty else p.default

        if type(default) is _DcField:
            raise TypeError(
                f"{n}: field() is dataclass syntax; in functions write the default "
                f"directly — it is fresh through the schema")

        params.append(_field_of(n, hints[n], default, cache))

    _validate_cache(cache)
    sig = Signature(name=fn.__name__, doc=fn.__doc__, params=tuple(params))
    return sig
