from dataclasses import dataclass

from pytypehint import signature_of, struct_of


@dataclass
class Node:
    child: "Node | None" = None


def test_compilations_have_distinct_identity_and_both_work():
    a = struct_of(Node)
    b = struct_of(Node)
    assert a is not b
    assert a != b
    assert a.build({}) == Node()
    assert b.build({}) == Node()


def test_recursive_struct_reuses_root_identity():
    schema = struct_of(Node)
    nested = next(shape for shape in schema.fields[0].shape if shape.pytype is Node)
    assert nested is schema


def test_fields_and_signatures_use_identity():
    a = struct_of(Node)
    b = struct_of(Node)
    assert a.fields[0] is not b.fields[0]
    assert a.fields[0] != b.fields[0]

    def fn(x: int = 0):
        pass

    assert signature_of(fn) != signature_of(fn)
