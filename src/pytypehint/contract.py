"""The portable form of a compiled schema.

`Struct.to_dict()` and `Signature.to_dict()` write the contract the core holds as
a JSON-compatible tree: dicts, lists, strings, numbers, booleans and null, and
nothing else. It describes what the schema accepts — types, options, limits,
notation, defaults — and takes no position on how any of it should be presented.
A wrapper reads it to build a form, a command line, a client in another language
or a fingerprint, and each decides for itself what its own medium makes of it.

Two properties are load-bearing and are what the format is designed around.

It is deterministic. Equal definitions produce equal documents, byte for byte,
across processes and hash seeds: every key is written in a fixed order, every
sequence keeps the order the author wrote, and nothing derived from `id()` or
from set iteration reaches the output.

It speaks the same portable language as `Struct.decode()`. A date is written the
way decode reads one, an enum member is written by the name decode looks up, and
a value that would be ambiguous in a portable tree carries the same
`$type`/`$value` wrapper decode reads. So a default taken from this document is
valid input to the pipeline — `build(decode(...))` returns it — with no
translation in between.

See docs/contract.md for the format itself.
"""

from datetime import date, time

from pytypehint.errors import SchemaValueError
from pytypehint.shapes import (
    Bool, Date, EnumShape, Float, Int, List, NoneShape, Str, Time,
)
from pytypehint.structure import Struct, _TYPE, _VALUE, _portable_options
from pytypehint.utils import MISSING
from pytypehint.validation import value_branch

# Raised only when a key already in the format changes meaning or leaves. New
# keys do not raise it: a reader is expected to ignore the ones it does not know,
# which is what makes an addition compatible.
_VERSION = 1

_TYPE_NAMES = {
    Int: "int", Float: "float", Str: "str", Bool: "bool", Date: "date",
    Time: "time", NoneShape: "none", List: "list", EnumShape: "enum",
    Struct: "struct",
}


# ---------------------------------------------------------------------------
# Portable values
# ---------------------------------------------------------------------------

# A value is written through its shape, never by inspecting the object: the
# schema decides the reading here exactly as it does in decode.
#
# Every slot goes through here — a field, a list item, a field of a nested
# dataclass — because the discriminator rule is about a slot and not about a
# field. A list of `str | date` needs each element to name its option just as the
# field would, and writing the element bare would hand decode a string it is
# right to leave alone and validation a `str` where the author put a `date`.
#
# Which option a value inhabits is decided by the core's own router, so it cannot
# drift from the option validation would select, and the router is asked the
# shapes themselves with nothing removed. Every check the core performs is
# answered by the schema and the value — no atom reads the filesystem, the
# environment, the working directory or the clock — so the option a default
# inhabits is the same in every process and at every moment, and so is the
# document written from it. That is the whole of why this is deterministic: there
# is no exception here to route around.
def _portable(shapes, value):
    shape = value_branch(shapes, value)
    if shape is None:
        # A certified default inhabits one of its options and nothing since can
        # have changed that, so reaching this means the schema was assembled by
        # hand and left half-compiled. It is a schema error like any other rather
        # than a bare TypeError.
        raise SchemaValueError(
            f"cannot describe {value!r}: it matches no option of this slot")
    written = _written(shape, value)

    if type(shape) is Struct:
        # A dataclass has room for the discriminator inside itself, and uses it
        # only where another dataclass could be meant.
        if len([s for s in shapes if type(s) is Struct]) > 1:
            return {_TYPE: shape.cls.__name__, **written}
        return written

    # The wrapper is needed exactly where the portable spelling of two options
    # collides — the same condition decode reads it under — so what this writes
    # is what decode consumes.
    if any(option is shape for option in _portable_options(shapes)):
        return {_TYPE: shape.option_id(), _VALUE: written}
    return written


def _written(shape, value):
    kind = type(shape)
    if kind is Date:
        return value.isoformat()
    if kind is Time:
        # Spelled out rather than left to `auto`, so the contract states the
        # precision instead of inheriting it from whatever the value carries.
        return value.isoformat(timespec="seconds")
    if kind is EnumShape:
        return value.name
    if kind is List:
        return [_portable(shape.item, item) for item in value]
    if kind is Struct:
        return {f.name: _portable(f.shape, getattr(value, f.name))
                for f in shape.fields}
    if kind is Float:
        return _as_float(value)
    return value


# `Min(0)` and `Min(0.0)` are equal atoms, so on a float shape both are written as
# a float — otherwise two schemas that compare equal would produce two documents.
# An integer with no float of equal value is left as it is: it has no float twin
# to normalize to, and this must not fail on a schema the core accepted.
#
# Two ways an integer can have no twin, and both are this: one is too large to
# convert at all, the other converts to a neighbour, because above 2**53 the
# floats thin out. Publishing the neighbour would state a bound the schema does
# not hold — `Min(2**53 + 1)` written as `9007199254740992.0` invites a value the
# core then rejects — so the answer is kept only when it is the same number.
def _as_float(value):
    try:
        restored = float(value)
    except OverflowError:
        return value
    return restored if restored == value else value


# A number an atom carries is normalized on the way out; a default's is not, and
# the difference between the two is the whole reason this is a separate function.
# `Min(0)`, `Min(0.0)` and `Min(-0.0)` are one atom — equal, and equal in hash —
# so the document they write has to be one document, and a signed zero would make
# it two. A default of `-0.0` is a value the author wrote: a field holding it is
# not equal to one holding `0.0`, so the sign is information there and is kept.
def _atom_number(value, *, as_float: bool):
    if not as_float:
        return value
    restored = _as_float(value)
    # `-0.0 + 0.0` is `0.0`, and every other float is left where it was. An
    # integer with no float twin is handed back untouched, sign and all.
    return restored + 0.0 if type(restored) is float else restored


# A bound carries a value from the ordered types only, so this covers all of them.
def _bound_value(value, *, as_float: bool):
    if type(value) is date:
        return value.isoformat()
    if type(value) is time:
        return value.isoformat(timespec="seconds")
    return _atom_number(value, as_float=as_float)


# ---------------------------------------------------------------------------
# Definition tables
# ---------------------------------------------------------------------------

class _Document:
    """Definitions collected while one document is written, and nothing beyond it.

    The tables live for a single call. Caching them across calls would hand two
    callers the same tree, and the promise is that each gets one it owns.
    """

    def __init__(self):
        self.structs: dict[str, dict] = {}
        self.enums: dict[str, dict] = {}
        self._struct_ids: dict[Struct, str] = {}
        self._enum_ids: dict[type, str] = {}
        # Where the ordinal search for each name left off, per table. The two
        # tables count apart because they are separate namespaces: a struct
        # named `T` must not push an enum named `T` to `T#2`.
        self._struct_ordinals: dict[str, int] = {}
        self._enum_ordinals: dict[str, int] = {}


# Two classes of the same name can sit in one schema whenever they are not
# options of one field, and no name distinguishes them: `__qualname__` repeats
# for two classes built by the same factory. So the id is the class name, made
# unique within this document by the order it was first reached. The readable
# name stays available as `name` — that is the string the wire carries, and the
# id is only a handle for pointing at a definition inside this document.
#
# The scan resumes where the last one for this name stopped, rather than starting
# at 2 every time: restarting makes n namesakes cost n² steps. It still scans,
# because a class may be named `T#2` outright and hold the id a namesake of `T`
# would otherwise be given.
def _identify(taken: dict[str, dict], ordinals: dict[str, int], name: str) -> str:
    if name not in taken:
        return name
    ordinal = ordinals.get(name, 2)
    while f"{name}#{ordinal}" in taken:
        ordinal += 1
    ordinals[name] = ordinal + 1
    return f"{name}#{ordinal}"


def _struct_ref(struct, doc: _Document) -> str:
    known = doc._struct_ids.get(struct)
    if known is not None:
        return known

    ident = _identify(doc.structs, doc._struct_ordinals, struct.cls.__name__)
    doc._struct_ids[struct] = ident
    # The slot is claimed before descending: a struct that reaches itself finds
    # its own id here and writes a reference instead of recurring forever. It
    # also fixes the table's key order as the order definitions were reached.
    doc.structs[ident] = {}
    doc.structs[ident] = {
        "name": struct.cls.__name__,
        "fields": [_field_node(f, doc) for f in struct.fields],
    }
    return ident


def _enum_ref(cls, doc: _Document) -> str:
    known = doc._enum_ids.get(cls)
    if known is not None:
        return known

    ident = _identify(doc.enums, doc._enum_ordinals, cls.__name__)
    doc._enum_ids[cls] = ident
    # Canonical members only. `list(cls)` leaves out aliases, which name a member
    # already listed; decode still accepts an alias, because the enum resolves it
    # to that same member.
    doc.enums[ident] = {"name": cls.__name__,
                        "members": [member.name for member in cls]}
    return ident


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def _shape_node(shape, doc: _Document, *, labelled: bool) -> dict:
    kind = type(shape)
    node: dict = {"type": _TYPE_NAMES[kind]}

    # The identity is what a discriminator would name, so it is written only
    # where there is something to discriminate.
    if labelled:
        node["id"] = shape.option_id()

    if kind is Struct:
        node["ref"] = _struct_ref(shape, doc)
        # A dataclass option carries no atoms of its own, so a Struct node ends here.
        return node

    if kind in (Int, Float, Date, Time):
        as_float = kind is Float
        if shape.min is not None:
            node["min"] = _bound_value(shape.min.value, as_float=as_float)
            if shape.min.exclusive:
                node["exclusive_min"] = True
        if shape.max is not None:
            node["max"] = _bound_value(shape.max.value, as_float=as_float)
            if shape.max.exclusive:
                node["exclusive_max"] = True
        if kind is Int and shape.multiple_of is not None:
            node["multiple_of"] = shape.multiple_of.value
        if shape.choices is not None:
            node["choices"] = [_bound_value(v, as_float=as_float)
                               for v in shape.choices.values]
        if kind in (Int, Float):
            if shape.step is not None:
                node["step"] = _atom_number(shape.step.value, as_float=as_float)
            if shape.slider is not None:
                node["slider"] = {"show_value": shape.slider.show_value}
        if shape.placeholder is not None:
            node["placeholder"] = shape.placeholder.value

    elif kind is Str:
        # A bound on a `str` measures its length, and the core rejects an
        # exclusive one, so these are named apart from a bound on a value.
        if shape.min is not None:
            node["min_length"] = shape.min.value
        if shape.max is not None:
            node["max_length"] = shape.max.value
        if shape.pattern is not None:
            node["pattern"] = shape.pattern.value
            if shape.pattern.message is not None:
                node["pattern_message"] = shape.pattern.message
        if shape.choices is not None:
            node["choices"] = list(shape.choices.values)
        if shape.file_hint is not None:
            mark: dict = {}
            if shape.file_hint.extensions:
                mark["extensions"] = list(shape.file_hint.extensions)
            if shape.file_hint.min_size is not None:
                mark["min_size"] = shape.file_hint.min_size
            if shape.file_hint.max_size is not None:
                mark["max_size"] = shape.file_hint.max_size
            # An empty object is the mark itself, with nothing narrowing it.
            node["file_hint"] = mark
        if shape.is_password is not None:
            node["is_password"] = True
        if shape.rows is not None:
            node["rows"] = shape.rows.value
        if shape.placeholder is not None:
            node["placeholder"] = shape.placeholder.value

    elif kind is List:
        if shape.min is not None:
            node["min_items"] = shape.min.value
        if shape.max is not None:
            node["max_items"] = shape.max.value
        # Singular, and never "items": in JSON Schema that word means positional
        # validation of a tuple, while this is the set of options one element may
        # take. The same word for two different things would be read wrong.
        node["item"] = _slot(shape.item, doc)

    elif kind is EnumShape:
        node["ref"] = _enum_ref(shape.cls, doc)

    extras = shape.extras
    if extras:
        node["extras"] = extras
    return node


def _slot(shapes, doc: _Document) -> list:
    labelled = len(shapes) > 1
    return [_shape_node(shape, doc, labelled=labelled) for shape in shapes]


def _field_node(f, doc: _Document) -> dict:
    node: dict = {"name": f.name}
    if f.label is not None:
        node["label"] = f.label.value
    if f.description is not None:
        node["description"] = f.description.value
    if f.optional_toggle is not None:
        # Written even when false: absent, true and false are three states, and
        # the false one says the toggle starts closed rather than saying nothing.
        node["optional_toggle"] = f.optional_toggle.enabled
    if f.default is not MISSING:
        # `null` appears here and nowhere else in the format, so it always means
        # one thing: the default is None. A field with no default omits the key.
        node["default"] = _portable(f.shape, f.default)
    node["shape"] = _slot(f.shape, doc)
    return node


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def _struct_document(struct) -> dict:
    doc = _Document()
    root = _struct_ref(struct, doc)
    # The root lives in the table like any other definition, because a recursive
    # field points back at it and needs somewhere to point.
    return {"v": _VERSION, "kind": "struct", "root": root,
            "defs": {"structs": doc.structs, "enums": doc.enums}}


def _signature_document(signature) -> dict:
    doc = _Document()
    # Parameters are written in place: nothing can hold a reference to a
    # signature, so there is no definition to point at.
    params = [_field_node(p, doc) for p in signature.params]

    document: dict = {"v": _VERSION, "kind": "signature", "name": signature.name}
    if signature.doc is not None:
        document["doc"] = signature.doc
    document["params"] = params
    document["defs"] = {"structs": doc.structs, "enums": doc.enums}
    return document
