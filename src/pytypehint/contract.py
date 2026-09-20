from datetime import date, time

from pytypehint.errors import SchemaValueError
from pytypehint.shapes import (
    Bool, Date, EnumShape, Float, Int, List, NoneShape, Str, Time, Tuple,
)
from pytypehint.structure import Struct, _TYPE, _VALUE, _portable_options
from pytypehint.utils import MISSING
from pytypehint.validation import value_branch

_VERSION = 1

_TYPE_NAMES = {
    Int: "int", Float: "float", Str: "str", Bool: "bool", Date: "date",
    Time: "time", NoneShape: "none", List: "list", EnumShape: "enum",
    Struct: "struct", Tuple: "tuple",
}


def _portable(shapes, value):
    shape = value_branch(shapes, value)
    if shape is None:
        raise SchemaValueError(
            f"cannot describe {value!r}: it matches no option of this slot")
    written = _written(shape, value)

    if type(shape) is Struct:
        if len([s for s in shapes if type(s) is Struct]) > 1:
            return {_TYPE: shape.cls.__name__, **written}
        return written

    if any(option is shape for option in _portable_options(shapes)):
        return {_TYPE: shape.option_id(), _VALUE: written}
    return written


def _written(shape, value):
    kind = type(shape)
    if kind is Date:
        return value.isoformat()
    if kind is Time:
        return value.isoformat(timespec="seconds")
    if kind is EnumShape:
        return value.name
    if kind is List:
        return [_portable(shape.item, item) for item in value]
    if kind is Tuple:
        return [_portable(shape._item_at(i), item) for i, item in enumerate(value)]
    if kind is Struct:
        return {f.name: _portable(f.shape, getattr(value, f.name))
                for f in shape.fields}
    if kind is Float:
        return _as_float(value)
    return value


def _as_float(value):
    try:
        restored = float(value)
    except OverflowError:
        return value
    return restored if restored == value else value


# Normalize atom signed zero, but preserve the sign of authored defaults.
def _atom_number(value, *, as_float: bool):
    if not as_float:
        return value
    restored = _as_float(value)
    return restored + 0.0 if type(restored) is float else restored


def _bound_value(value, *, as_float: bool):
    if type(value) is date:
        return value.isoformat()
    if type(value) is time:
        return value.isoformat(timespec="seconds")
    return _atom_number(value, as_float=as_float)


class _Document:

    def __init__(self):
        self.structs: dict[str, dict] = {}
        self.enums: dict[str, dict] = {}
        self._struct_ids: dict[Struct, str] = {}
        self._enum_ids: dict[type, str] = {}
        self._struct_ordinals: dict[str, int] = {}
        self._enum_ordinals: dict[str, int] = {}


# Resume name suffixes to avoid quadratic scans for repeated class names.
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
    # Register before descending so recursive fields find their own definition.
    doc.structs[ident] = {}
    # A comprehension adds a recursion frame on Python < 3.12.
    fields = []
    for f in struct.fields:
        fields.append(_field_node(f, doc))
    doc.structs[ident] = {"name": struct.cls.__name__, "fields": fields}
    return ident


def _enum_ref(cls, doc: _Document) -> str:
    known = doc._enum_ids.get(cls)
    if known is not None:
        return known

    ident = _identify(doc.enums, doc._enum_ordinals, cls.__name__)
    doc._enum_ids[cls] = ident
    doc.enums[ident] = {"name": cls.__name__,
                        "members": [member.name for member in cls]}
    return ident


def _shape_node(shape, doc: _Document, *, labelled: bool) -> dict:
    kind = type(shape)
    node: dict = {"type": _TYPE_NAMES[kind]}

    if labelled:
        node["id"] = shape.option_id()

    if kind is Struct:
        node["ref"] = _struct_ref(shape, doc)
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
        node["item"] = _slot(shape.item, doc)

    elif kind is Tuple:
        if shape.min is not None:
            node["min_items"] = shape.min.value
        if shape.max is not None:
            node["max_items"] = shape.max.value
        if shape.variadic:
            node["item"] = _slot(shape.items[0], doc)
        else:
            node["items"] = [_slot(options, doc) for options in shape.items]

    elif kind is EnumShape:
        node["ref"] = _enum_ref(shape.cls, doc)

    extras = shape.extras
    if extras:
        node["extras"] = extras
    return node


def _slot(shapes, doc: _Document) -> list:
    labelled = len(shapes) > 1
    # A comprehension adds a recursion frame on Python < 3.12.
    nodes = []
    for shape in shapes:
        nodes.append(_shape_node(shape, doc, labelled=labelled))
    return nodes


def _field_node(f, doc: _Document) -> dict:
    node: dict = {"name": f.name}
    if f.label is not None:
        node["label"] = f.label.value
    if f.description is not None:
        node["description"] = f.description.value
    if f.optional_toggle is not None:
        node["optional_toggle"] = f.optional_toggle.enabled
    if f.default is not MISSING:
        node["default"] = _portable(f.shape, f.default)
    node["shape"] = _slot(f.shape, doc)
    return node


def _struct_document(struct) -> dict:
    doc = _Document()
    root = _struct_ref(struct, doc)
    return {"v": _VERSION, "kind": "struct", "root": root,
            "defs": {"structs": doc.structs, "enums": doc.enums}}


def _signature_document(signature) -> dict:
    doc = _Document()
    params = [_field_node(p, doc) for p in signature.params]

    document: dict = {"v": _VERSION, "kind": "signature", "name": signature.name}
    if signature.doc is not None:
        document["doc"] = signature.doc
    document["params"] = params
    document["defs"] = {"structs": doc.structs, "enums": doc.enums}
    return document
