from dataclasses import dataclass, field
from typing import Annotated

import pytest

from pytypehint import Max, signature_of, struct_of


@dataclass
class Page:
    n: int = 1


@dataclass
class Query:
    page: Page = field(default_factory=Page)
    tags: list[str] = field(default_factory=list)


def test_struct_build_constructs_nested_data_and_fresh_defaults():
    schema = struct_of(Query)
    a = schema.build({"page": {"n": 2}})
    b = schema.build({})
    assert a == Query(Page(2), [])
    assert b == Query(Page(1), [])
    assert a.tags is not b.tags


def test_readme_nested_error_message():
    @dataclass(frozen=True)
    class LimitedPage:
        size: Annotated[int, Max(100)] = 20

    @dataclass
    class Search:
        page: LimitedPage = LimitedPage()

    with pytest.raises(ValueError) as info:
        struct_of(Search).build({"page": {"size": 500}})
    assert str(info.value) == "page: size: too large: 500, maximum 100"


def test_signature_build_returns_constructed_kwargs_without_execution():
    called = []

    def run(page: Page):
        called.append(page)

    kwargs = signature_of(run).build({"page": {"n": 2}})
    assert kwargs == {"page": Page(2)}
    assert called == []


def test_instance_input_is_rejected_at_field_and_list_depth():
    with pytest.raises(TypeError, match=r"^expected dict, got Query instance$"):
        struct_of(Query).build(Query("q"))
    with pytest.raises(TypeError, match=r"^expected dict, got Query instance$"):
        struct_of(Query).resolve(Query("q"))

    with pytest.raises(TypeError, match=r"^page: expected dict, got Page instance$"):
        struct_of(Query).build({"page": Page()})

    @dataclass
    class Batch:
        pages: list[Page]

    with pytest.raises(TypeError, match=r"^pages: \[0\]: expected dict, got Page instance$"):
        struct_of(Batch).build({"pages": [Page()]})


def test_instance_defaults_remain_supported():
    seed = Page(4)

    def run(page: Page = seed):
        pass

    a = signature_of(run).build({})["page"]
    b = signature_of(run).build({})["page"]
    assert a == b == seed
    assert a is not b and a is not seed


def test_struct_instance_default_crosses_build_after_rematerialization():
    @dataclass(frozen=True)
    class Seed:
        n: int = 4

    @dataclass
    class Holder:
        seed: Seed = Seed()

    first = struct_of(Holder).build({})
    second = struct_of(Holder).build({})
    assert first == second == Holder(Seed(4))
    assert first.seed is not second.seed
