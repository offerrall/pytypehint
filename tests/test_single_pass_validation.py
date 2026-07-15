"""build validates the input tree once and constructs directly.

docs/comparison.md, 'Cost': 'build validates the input tree once and constructs
directly [...] the cost is linear in the size of the input.'
"""

from dataclasses import dataclass, field, make_dataclass
from typing import Annotated

import pytest

from pytypehint import Max, signature_of, struct_of
from pytypehint import structure


# ------------------------------------------------- nested defaults still work


def test_impure_nested_default_still_fails_with_the_documented_path():
    """docs/restrictions.md, 'Impure default': 'leaf: n: default: too large: 2, maximum 1'.

    The single-pass change removes the revalidation of *present* keys only.
    Absent keys are still rematerialized and validated at their own depth, which
    is what makes an impure recipe observable.
    """
    counter = iter(range(1, 100))

    @dataclass
    class Leaf:
        n: Annotated[int, Max(1)] = field(default_factory=lambda: next(counter))

    @dataclass
    class Root:
        leaf: Leaf

    # The first serving certifies the schema at 1; the second drifts to 2.
    schema = struct_of(Root)

    with pytest.raises(ValueError) as error:
        schema.build({"leaf": {}})

    assert str(error.value) == "leaf: n: default: too large: 2, maximum 1"


def test_absent_nested_defaults_are_filled_and_constructed():
    """docs/defaults.md: a default 'is certified when the schema compiles and rematerialized whenever a build or resolve omits its key'."""
    @dataclass
    class Leaf:
        size: int = 20

    @dataclass
    class Middle:
        leaf: Leaf = field(default_factory=Leaf)

    @dataclass
    class Root:
        middle: Middle = field(default_factory=Middle)
        name: str = "root"

    built = struct_of(Root).build({})

    assert built == Root(middle=Middle(leaf=Leaf(size=20)), name="root")


def test_defaults_are_filled_below_a_partially_supplied_input():
    """docs/defaults.md: 'A provided key never runs its recipe' — the absent siblings below it still do."""
    @dataclass
    class Leaf:
        size: int = 20
        label: str = "leaf"

    @dataclass
    class Middle:
        leaf: Leaf = field(default_factory=Leaf)

    @dataclass
    class Root:
        middle: Middle = field(default_factory=Middle)

    built = struct_of(Root).build({"middle": {"leaf": {"size": 50}}})

    assert built == Root(middle=Middle(leaf=Leaf(size=50, label="leaf")))


def test_nested_list_defaults_are_rematerialized_fresh_per_build():
    """docs/defaults.md: 'list | fresh list; items rematerialized recursively'."""
    @dataclass
    class Leaf:
        tags: list[str] = field(default_factory=list)

    @dataclass
    class Root:
        leaf: Leaf = field(default_factory=Leaf)

    schema = struct_of(Root)
    first = schema.build({})
    second = schema.build({})

    assert first.leaf.tags == [] and second.leaf.tags == []
    assert first.leaf.tags is not second.leaf.tags


def test_invalid_present_value_still_reports_the_full_path():
    """README: `str(error) == "page: size: too large: 500, maximum 100"` — the outer resolve is the one and only validation."""
    @dataclass
    class Page:
        size: Annotated[int, Max(100)] = 20

    @dataclass
    class Search:
        page: Page = field(default_factory=Page)

    with pytest.raises(ValueError) as error:
        struct_of(Search).build({"page": {"size": 500}})

    assert str(error.value) == "page: size: too large: 500, maximum 100"


# ------------------------------------------------- $type across resolve/build


@dataclass
class File:
    path: str


@dataclass
class Url:
    value: str


@dataclass
class Sources:
    items: list[File | Url] = field(default_factory=list)


@dataclass
class Payload:
    sources: Sources = field(default_factory=Sources)


@dataclass
class Envelope:
    payload: Payload = field(default_factory=Payload)


_DEEP = {"payload": {"sources": {"items": [
    {"$type": "Url", "value": "https://example.test"},
    {"$type": "File", "path": "/tmp/x"},
]}}}


def test_resolve_preserves_type_at_depth_three_inside_a_list_item():
    """docs/resolve.md: 'For a dataclass union, resolve validates `$type` and preserves it'."""
    resolved = struct_of(Envelope).resolve(_DEEP)

    assert resolved == _DEEP
    assert resolved["payload"]["sources"]["items"][0]["$type"] == "Url"
    assert resolved["payload"]["sources"]["items"][1]["$type"] == "File"


def test_build_consumes_type_at_depth_three_inside_a_list_item():
    """docs/build.md: 'build removes the discriminator when constructing the selected class' and 'Discrimination works at every nesting depth and in union-valued list items'."""
    built = struct_of(Envelope).build(_DEEP)

    assert built == Envelope(payload=Payload(sources=Sources(items=[
        Url(value="https://example.test"),
        File(path="/tmp/x"),
    ])))


def test_build_leaves_the_input_dict_untouched_while_consuming_type():
    """docs/build.md: `$type` is consumed by construction, not stripped from the caller's data."""
    data = {"payload": {"sources": {"items": [{"$type": "Url", "value": "u"}]}}}

    struct_of(Envelope).build(data)

    assert data == {"payload": {"sources": {"items": [{"$type": "Url", "value": "u"}]}}}


def test_missing_discriminator_at_depth_three_reports_the_full_path():
    """docs/build.md: 'value: ambiguous dict: field accepts File | Url — add "$type" naming the variant'."""
    data = {"payload": {"sources": {"items": [{"value": "u"}]}}}

    with pytest.raises(TypeError) as error:
        struct_of(Envelope).build(data)

    assert str(error.value) == (
        'payload: sources: items: [0]: ambiguous dict: field accepts File | Url '
        '— add "$type" naming the variant')


def test_unknown_discriminator_at_depth_three_reports_the_full_path():
    """docs/build.md: "value: $type: not a choice: 'Other', expected one of ('File', 'Url')"."""
    data = {"payload": {"sources": {"items": [{"$type": "Other", "value": "u"}]}}}

    with pytest.raises(ValueError) as error:
        struct_of(Envelope).build(data)

    assert str(error.value) == (
        "payload: sources: items: [0]: $type: not a choice: 'Other', "
        "expected one of ('File', 'Url')")


def test_non_string_discriminator_at_depth_three_reports_the_full_path():
    """docs/build.md: 'value: $type: expected str, got int'."""
    data = {"payload": {"sources": {"items": [{"$type": 1, "value": "u"}]}}}

    with pytest.raises(TypeError) as error:
        struct_of(Envelope).build(data)

    assert str(error.value) == "payload: sources: items: [0]: $type: expected str, got int"


def test_signature_build_inherits_single_pass_validation():
    """docs/build.md: 'Signature.build(data) returns validated, constructed keyword arguments' — it reuses the same construction path."""
    def run(envelope: Envelope):
        return envelope

    built = signature_of(run).build({"envelope": _DEEP})

    assert built == {"envelope": Envelope(payload=Payload(sources=Sources(items=[
        Url(value="https://example.test"),
        File(path="/tmp/x"),
    ])))}


# ------------------------------------------------------------- empirical cost


def _chain(depth: int) -> type:
    """A chain of `depth` structs: L0 holds the int, each Lk holds an L(k-1)."""
    cls = make_dataclass("L0", [("size", Annotated[int, Max(100)], field(default=1))])
    for k in range(1, depth):
        cls = make_dataclass(f"L{k}", [("nxt", cls, field(default_factory=cls))])
    return cls


def _nest(depth: int) -> dict:
    data: dict = {"size": 1}
    for _ in range(1, depth):
        data = {"nxt": data}
    return data


def _count_validations(struct, data, monkeypatch) -> int:
    original = structure.Field._check_value_data
    calls = []

    def spy(self, value):
        calls.append(1)
        return original(self, value)

    monkeypatch.setattr(structure.Field, "_check_value_data", spy)
    try:
        struct.build(data)
    finally:
        monkeypatch.undo()
    return len(calls)


@pytest.mark.slow
def test_build_validates_a_struct_chain_linearly(monkeypatch):
    """Fija la garantía O(N) de docs/comparison.md: 'the cost is linear in the size of the input'.

    Counts how many present values a single build validates over a struct chain
    of depth N, generated on the fly. Each of the N levels is validated exactly
    once, by the outer resolve; construction adds none.

    This replaces the quadratic count this suite used to pin. If it ever goes
    superlinear again, the revalidation came back: fix the code, not this test.
    """
    counts = {depth: _count_validations(struct_of(_chain(depth)), _nest(depth), monkeypatch)
              for depth in (8, 12)}

    assert counts == {8: 8, 12: 12}

    # Linear: scaling the depth by 1.5 scales the work by 1.5, not by 1.5**2.
    assert counts[12] / counts[8] == 12 / 8


@pytest.mark.slow
@pytest.mark.parametrize("depth", [1, 2, 3, 4, 6, 8, 12, 16])
def test_validation_count_is_exactly_the_depth(depth, monkeypatch):
    """docs/comparison.md, 'Cost': every value in the input tree is validated exactly once."""
    struct = struct_of(_chain(depth))

    assert _count_validations(struct, _nest(depth), monkeypatch) == depth


# -------------------------------------------- input mutation is undefined


def test_input_mutation_during_construction_is_not_detected():
    """docs/build.md, 'Errors and constructors': 'Mutating the input during construction is undefined behaviour' — characterisation, not a contract.

    Two sibling fields share one dict; constructing the first runs a
    __post_init__ that mutates it out of schema, and the second field is then
    built from the mutated dict. Before the single-pass change, construction
    revalidated present keys and this specific ordering raised
    `ValueError: n: too large: 999, maximum 10`. The loss is intentional: that
    detection was partial and field-order dependent, so it was never a promise
    the core could keep — see docs/build.md and docs/defaults.md.

    This test records what happens today for one ordering. It is NOT a guarantee
    that mutation never raises: the outcome of mutating input during
    construction is undefined, and a future ordering or shape may well raise.
    """
    mutate: list[dict] = []

    @dataclass
    class Leaf:
        n: Annotated[int, Max(10)] = 1

        def __post_init__(self):
            for d in mutate:
                d["n"] = 999

    @dataclass
    class Twin:
        left: Leaf
        right: Leaf

    shared = {"n": 1}
    mutate.append(shared)

    built = struct_of(Twin).build({"left": shared, "right": shared})

    # Observed, not promised: the mutation rode into `right` unchecked.
    assert built.right.n == 999


def test_resolve_hands_back_the_caller_s_own_nested_dict():
    """docs/resolve.md: resolve 'do[es] not construct nested dataclass dictionaries' — the nested dict is passed through, not copied.

    This aliasing is why input mutation during construction cannot be policed
    cheaply, and therefore why docs/build.md leaves it undefined.
    """
    @dataclass
    class Page:
        size: int = 20

    @dataclass
    class Search:
        page: Page = field(default_factory=Page)

    page = {"size": 50}

    resolved = struct_of(Search).resolve({"page": page})

    assert resolved == {"page": {"size": 50}}
    assert resolved["page"] is page
