from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint.atoms import Label, Min
from pytypehint.bridge import struct_of


@dataclass
class Node:
    value: Annotated[int, Min(value=0)] = 0
    child: "Node | None" = None


def test_direct_recursion_is_one_object():
    s = struct_of(Node)
    assert s.fields[1].name == "child"
    assert s.fields[1].shape[0] is s


def test_direct_recursion_check_valid():
    s = struct_of(Node)
    s._check(Node())
    s._check(Node(value=1, child=Node(value=2, child=Node(value=3))))


def test_direct_recursion_check_invalid_at_root():
    s = struct_of(Node)
    with pytest.raises(ValueError, match=r"^value: too small: -1"):
        s._check(Node(value=-1))


def test_direct_recursion_check_invalid_nested():
    s = struct_of(Node)
    with pytest.raises(ValueError, match=r"^child: value: too small: -1"):
        s._check(Node(child=Node(value=-1)))


def test_direct_recursion_check_deep_tree():
    s = struct_of(Node)
    s._check(Node(value=0, child=Node(value=1, child=Node(value=2, child=Node(value=3)))))
    with pytest.raises(ValueError, match=r"^child: child: child: value: too small"):
        s._check(Node(child=Node(child=Node(child=Node(value=-1)))))


@dataclass
class Tree:
    value: Annotated[int, Min(value=0)] = 0
    children: "list[Tree]" = field(default_factory=list)


def test_list_recursion_is_one_object():
    s = struct_of(Tree)
    assert s.fields[1].shape[0].item[0] is s


def test_list_recursion_check_valid():
    s = struct_of(Tree)
    s._check(Tree())
    s._check(Tree(value=0, children=[Tree(value=1), Tree(value=2, children=[Tree(value=3)])]))


def test_list_recursion_check_invalid_nested():
    s = struct_of(Tree)
    with pytest.raises(ValueError, match=r"^children: \[0\]: value: too small: -1"):
        s._check(Tree(children=[Tree(value=-1)]))


def test_list_recursion_check_deep_tree():
    s = struct_of(Tree)
    deep = Tree(children=[Tree(children=[Tree(children=[Tree(value=5)])])])
    s._check(deep)


@dataclass
class MutualA:
    b: "MutualB | None" = None


@dataclass
class MutualB:
    a: "MutualA | None" = None


def test_mutual_recursion_closes_the_loop():
    a = struct_of(MutualA)
    b = a.fields[0].shape[0]
    assert b.cls is MutualB
    assert b.fields[0].shape[0] is a


def test_mutual_recursion_check():
    s = struct_of(MutualA)
    s._check(MutualA())
    s._check(MutualA(b=MutualB(a=MutualA(b=MutualB()))))
    with pytest.raises(TypeError, match=r"^b: expected MutualB"):
        s._check(MutualA(b=5))


@dataclass
class Deep3A:
    b: "Deep3B | None" = None


@dataclass
class Deep3B:
    c: "Deep3C | None" = None


@dataclass
class Deep3C:
    a: "Deep3A | None" = None


def test_three_hop_recursion_closes_the_loop():
    a = struct_of(Deep3A)
    b = a.fields[0].shape[0]
    c = b.fields[0].shape[0]
    assert (b.cls, c.cls) == (Deep3B, Deep3C)
    assert c.fields[0].shape[0] is a


def test_three_hop_recursion_check():
    s = struct_of(Deep3A)
    s._check(Deep3A())
    s._check(Deep3A(b=Deep3B(c=Deep3C(a=Deep3A()))))
    with pytest.raises(TypeError, match=r"^b: c: expected Deep3C"):
        s._check(Deep3A(b=Deep3B(c=5)))


def test_two_compilations_of_the_same_class_have_distinct_identity():
    assert struct_of(Node) != struct_of(Node)
    assert struct_of(Tree) != struct_of(Tree)
    assert struct_of(MutualA) != struct_of(MutualA)


@dataclass
class NodeTwin:
    value: Annotated[int, Min(value=0)] = 0
    child: "NodeTwin | None" = None


def test_recursive_structs_of_different_classes_are_not_equal():
    assert struct_of(Node) != struct_of(NodeTwin)


def test_recursive_hash_does_not_explode():
    assert isinstance(hash(struct_of(Node)), int)
    {struct_of(Node), struct_of(Tree), struct_of(MutualA)}


def test_recursive_field_default_is_validated():
    s = struct_of(Node)
    assert s.fields[1].default is None


@dataclass
class BadDefault:
    value: Annotated[int, Min(value=0)] = -1
    child: "BadDefault | None" = None


def test_recursive_field_bad_default_is_rejected():
    with pytest.raises(ValueError, match="too small"):
        struct_of(BadDefault)


@dataclass
class Leaf:
    n: int = 0


@dataclass
class Diamond:
    left: "Leaf | None" = None
    right: "Leaf | None" = None


def test_diamond_shares_one_struct():
    s = struct_of(Diamond)
    assert s.fields[0].shape[0] is s.fields[1].shape[0]


def test_recursive_fields_have_distinct_identity():
    a = struct_of(Node).fields[1]
    b = struct_of(Node).fields[1]
    assert a != b

    tree_a = struct_of(Tree).fields[1]
    tree_b = struct_of(Tree).fields[1]
    assert tree_a != tree_b


def test_union_collapses_duplicate_struct_before_it_reaches_a_shape():
    assert (Node | Node) is Node

    @dataclass
    class Holder:
        x: "Node | Node" = field(default_factory=Node)

    (f,) = struct_of(Holder).fields
    assert len(f.shape) == 1
    assert f.shape[0].cls is Node


def test_annotated_cannot_smuggle_a_second_struct_option():
    @dataclass
    class Holder:
        x: "Annotated[Node, Min(value=0)] | Node" = None

    with pytest.raises(TypeError, match="unsupported metadata for dataclass"):
        struct_of(Holder)


def test_hoisted_field_atom_cannot_smuggle_a_duplicate_struct_option():
    # Label is a field atom, hoisted (not "unsupported metadata"), so the two
    # options both compile to Struct(Node): a duplicate that the not-yet-ready
    # The deferred certification catches this before runtime.
    @dataclass
    class Holder:
        x: "Annotated[Node, Label('here')] | Node" = None

    with pytest.raises(ValueError, match="Field 'x': duplicate option types in shape"):
        struct_of(Holder)
