import copy
import gc
import inspect
import pickle
import weakref
from dataclasses import FrozenInstanceError, dataclass, field, is_dataclass, replace
from datetime import date, time
from enum import Enum
from typing import Annotated, Literal

import pytest
from hypothesis import given, strategies as st

from pytypehint import (Max, Min, Pattern, SchemaTypeError, SchemaValueError,
                        immutable, struct_of)
from pytypehint.shapes import Int


@immutable
class Exposure:
    stops: float = 0.0


@immutable
class Layer:
    name: Annotated[str, Min(1)]
    effect: Exposure
    color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)


@immutable
class Node:
    value: int
    children: 'tuple[Node, ...]' = ()


@immutable
class Base:
    x: int = 1


@immutable
class Derived(Base):
    y: Annotated[int, Min(1)] = 2


def test_normal_dataclass_and_replace():
    value = Exposure(stops=1.5)
    assert is_dataclass(value)
    assert not hasattr(value, '__dict__')
    assert replace(value, stops=2.0) == Exposure(stops=2.0)
    assert value.stops == 1.5
    with pytest.raises(FrozenInstanceError):
        value.stops = 2.0
    with pytest.raises(SchemaTypeError, match='expected float'):
        replace(value, stops=2)
    signature = inspect.signature(Exposure)
    assert signature.parameters['stops'].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize('value', [True, 2, '2', float('inf'), float('nan')])
def test_exact_finite_values(value):
    with pytest.raises((SchemaTypeError, SchemaValueError)):
        Exposure(stops=value)


def test_constraints_and_tuple_error_paths():
    @immutable
    class Settings:
        size: Annotated[int, Min(1), Max(2048)]
        rgb: tuple[int, Annotated[int, Min(1)], int]
        name: Annotated[str, Pattern('[a-z]+')] = 'brush'
        mode: Literal['paint', 'erase'] = 'paint'

    valid = Settings(size=32, rgb=(0, 1, 0))
    with pytest.raises(SchemaValueError) as error:
        replace(valid, rgb=(0, 0, 0))
    assert error.value.path == ('rgb', 1)
    for changes in ({'size': 0}, {'size': 2049}, {'name': '123'}, {'mode': 'other'},
                    {'rgb': (1, 2)}, {'rgb': [1, 2, 3]}, {'size': True}):
        with pytest.raises((SchemaTypeError, SchemaValueError)):
            replace(valid, **changes)


@pytest.mark.parametrize('hint', [list[int], tuple[list[int], ...], list[int] | None,
                                 dict[str, int], set[int], object])
def test_reject_mutable_or_unknown_field_types(hint):
    @immutable
    class Invalid:
        value: hint = None

    with pytest.raises(TypeError, match='immutable'):
        Invalid()


def test_reject_ordinary_frozen_dataclasses_and_enums():
    @dataclass(frozen=True)
    class Ordinary:
        x: int = 1

    class Choice(Enum):
        a = [1]

    for hint in (Ordinary, Choice):
        @immutable
        class Invalid:
            value: hint

        with pytest.raises(TypeError, match='immutable'):
            Invalid(value=None)


def test_reject_invalid_unused_model_branch():
    @immutable
    class Bad:
        values: list[int]

    @immutable
    class Outer:
        child: Bad | None = None

    with pytest.raises(TypeError, match='immutable'):
        Outer()


def test_defaults_execute_only_when_needed_once():
    calls = []

    def factory():
        calls.append(1)
        return (1, 2)

    @immutable
    class Values:
        items: tuple[int, ...] = field(default_factory=factory)

    assert Values(items=(4,)).items == (4,)
    assert calls == []
    assert Values().items == (1, 2)
    assert calls == [1]
    assert Values().items == (1, 2)
    assert calls == [1, 1]


def test_invalid_effective_default_rejected_without_poisoning_schema():
    @immutable
    class Value:
        size: int = 'bad'

    assert Value(size=4).size == 4
    with pytest.raises(SchemaTypeError) as error:
        Value()
    assert error.value.path == ('size',)
    assert Value(size=5).size == 5


def test_nested_instances_keep_identity_and_reject_unvalidated_objects():
    effect = Exposure(stops=1.0)
    layer = Layer(name='Photo', effect=effect)
    assert layer.effect is effect
    assert replace(layer, name='Edited').effect is effect
    with pytest.raises(SchemaTypeError):
        Layer(name='Photo', effect={'stops': 1.0})
    forged = object.__new__(Exposure)
    object.__setattr__(forged, 'stops', 1.0)
    with pytest.raises(SchemaValueError, match='successfully constructed'):
        Layer(name='Photo', effect=forged)


def test_failed_constructor_does_not_certify_leaked_instance():
    leaked = []

    @immutable
    class Bad:
        value: int
        def __post_init__(self):
            leaked.append(self)

    @immutable
    class Parent:
        value: Bad

    with pytest.raises(SchemaTypeError):
        Bad(value='bad')
    with pytest.raises(SchemaValueError, match='successfully constructed'):
        Parent(value=leaked[0])


def test_post_init_changes_are_validated():
    @immutable
    class Value:
        size: Annotated[int, Min(1)]
        def __post_init__(self):
            object.__setattr__(self, 'size', -1)

    with pytest.raises(SchemaValueError):
        Value(size=1)


def test_recursive_self_reference_is_not_a_validated_child():
    @immutable
    class Cycle:
        child: 'Cycle | None' = None
        def __post_init__(self):
            object.__setattr__(self, 'child', self)

    # Local forward references have the same namespace requirement as get_type_hints.
    Cycle.__annotations__['child'] = Cycle | None
    with pytest.raises(SchemaValueError, match='successfully constructed'):
        Cycle()


def test_recursive_validation_only_visits_new_values(monkeypatch):
    count = 0
    original = Int._check

    def counted(self, value):
        nonlocal count
        count += 1
        return original(self, value)

    monkeypatch.setattr(Int, '_check', counted)
    node = Node(value=0)
    for index in range(1, 101):
        node = Node(value=index, children=(node,))
    assert count == 101
    assert node.children[0].value == 99
    with pytest.raises(SchemaTypeError) as error:
        Node(value=1, children=(node, 42))
    assert error.value.path == ('children', 1)


def test_tuple_variants_reuse_standard_union_validation():
    @immutable
    class Values:
        items: tuple[int, ...] | tuple[str, ...]

    assert Values(items=(1, 2)).items == (1, 2)
    assert Values(items=('a',)).items == ('a',)
    with pytest.raises(SchemaValueError, match='matches no option'):
        Values(items=(1, 'a'))


def test_inheritance_requires_decorator_on_each_subclass():
    assert Derived(x=3, y=4).x == 3
    with pytest.raises(SchemaValueError):
        Derived(y=0)

    class Unchecked(Base):
        y: str

    with pytest.raises(SchemaTypeError, match='subclasses'):
        Unchecked()
    with pytest.raises(TypeError, match='bases'):
        @immutable
        class WithDictionary(dict):
            value: int


def test_reinitialization_is_blocked():
    obj = Exposure(stops=1.5)
    with pytest.raises(FrozenInstanceError):
        obj.__init__(stops=9.0)
    assert obj.stops == 1.5


def test_copy_and_pickle_keep_validated_contract():
    value = Layer(name='Photo', effect=Exposure(stops=1.0))
    assert copy.copy(value) is value
    assert copy.deepcopy(value) is value
    restored = pickle.loads(pickle.dumps(value))
    assert restored == value
    assert restored is not value
    assert Layer(name='Other', effect=restored.effect).effect is restored.effect


def test_certification_does_not_keep_instances_alive():
    value = Exposure()
    reference = weakref.ref(value)
    del value
    gc.collect()
    assert reference() is None


def test_standard_schema_entry_points_still_work():
    schema = struct_of(Layer)
    data = {'name': 'Photo', 'effect': {'stops': 1.0}}
    assert schema.resolve(data)['effect'] is data['effect']
    value = schema.build(data)
    assert value == Layer(name='Photo', effect=Exposure(stops=1.0))
    assert schema.to_dict()
    decoded = schema.decode({**data, 'color': [0.0, 0.0, 0.0, 1.0]})
    assert schema.build(decoded) == value


def test_temporal_values_remain_strict():
    @immutable
    class Schedule:
        day: date
        hour: time

    assert Schedule(day=date(2026, 9, 21), hour=time(10)).hour == time(10)
    with pytest.raises(SchemaValueError):
        Schedule(day=date(2026, 9, 21), hour=time(10, microsecond=1))


def test_custom_initialization_and_double_decoration_are_rejected():
    with pytest.raises(TypeError, match='__init__'):
        @immutable
        class Custom:
            def __init__(self):
                pass

    with pytest.raises(TypeError, match='not both'):
        immutable(Exposure)


def test_reentrant_initialization_cannot_certify_a_partial_instance():
    @immutable
    class Reentrant:
        value: int = 1
        def __post_init__(self):
            self.__init__(value=2)

    with pytest.raises(FrozenInstanceError, match='reinitialize'):
        Reentrant()


def test_tuple_constraints_apply_even_with_validated_children():
    @immutable
    class Collection:
        children: Annotated[tuple[Exposure, ...], Min(1), Max(2)]

    item = Exposure()
    assert Collection(children=(item,)).children[0] is item
    for values in ((), (item, item, item)):
        with pytest.raises(SchemaValueError) as error:
            Collection(children=values)
        assert error.value.path == ('children',)


def test_readme_models_round_trip():
    channel = Annotated[float, Min(0.0), Max(1.0)]

    @immutable
    class Grayscale:
        pass

    @immutable
    class Picture:
        effect: Exposure | Grayscale
        color: tuple[channel, channel, channel, channel] = (0.0, 0.0, 0.0, 1.0)

    @immutable
    class Document:
        size: tuple[Annotated[int, Min(1)], Annotated[int, Min(1)]]
        layers: tuple[Picture, ...] = ()

    photo = Picture(effect=Exposure(stops=1.5))
    original = Document(size=(1920, 1080), layers=(photo,))
    resized = replace(original, size=(3840, 2160))
    assert resized.layers[0] is photo
    schema = struct_of(Document)
    loaded = schema.build(schema.decode({'size': [1920, 1080], 'layers': [
        {'effect': {'$type': 'Exposure', 'stops': 1.5}},
    ]}))
    assert loaded == original
    assert schema.to_dict()


def test_no_generated_state_mutator():
    value = Derived()
    assert not hasattr(value, '__setstate__')
    with pytest.raises(FrozenInstanceError):
        del value.x
    assert value.x == 1


@pytest.mark.parametrize('protocol', range(pickle.HIGHEST_PROTOCOL + 1))
def test_pickle_protocols_preserve_shared_children(protocol):
    child = Node(value=2)
    root = Node(value=1, children=(child, child))
    restored = pickle.loads(pickle.dumps(root, protocol=protocol))
    assert restored == root
    assert restored.children[0] is restored.children[1]
    assert Node(value=0, children=(restored,)).children[0] is restored


@pytest.mark.parametrize('operation', [copy.copy, copy.deepcopy, pickle.dumps])
def test_copy_and_pickle_reject_unconstructed_instances(operation):
    value = object.__new__(Exposure)
    object.__setattr__(value, 'stops', 0.0)
    with pytest.raises(SchemaValueError, match='successfully constructed'):
        operation(value)


def test_pickle_reconstruction_validates_values():
    reconstruct, arguments = Exposure().__reduce_ex__(pickle.HIGHEST_PROTOCOL)
    cls, values = arguments
    values['stops'] = 'bad'
    with pytest.raises(SchemaTypeError):
        reconstruct(cls, values)


def test_failed_post_init_cleans_up_and_does_not_certify():
    leaked = []

    @immutable
    class Value:
        fail: bool = False

        def __post_init__(self):
            if self.fail:
                leaked.append(self)
                raise RuntimeError('hook failed')

    @immutable
    class Parent:
        value: Value

    with pytest.raises(RuntimeError, match='hook failed'):
        Value(fail=True)
    with pytest.raises(SchemaValueError, match='successfully constructed'):
        Parent(value=leaked[0])
    assert Parent(value=Value()).value.fail is False


def test_factory_failure_and_invalid_result_do_not_poison_later_construction():
    results = iter([RuntimeError('factory failed'), [], (1,)])

    def factory():
        value = next(results)
        if isinstance(value, Exception):
            raise value
        return value

    @immutable
    class Value:
        items: tuple[int, ...] = field(default_factory=factory)

    with pytest.raises(RuntimeError, match='factory failed'):
        Value()
    with pytest.raises(SchemaTypeError) as error:
        Value()
    assert error.value.path == ('items',)
    assert Value().items == (1,)


def test_invalid_dependency_does_not_publish_partial_contract():
    @immutable
    class Invalid:
        mutable: list[int]

    @immutable
    class Parent:
        child: Invalid | None = None

    for _ in range(3):
        with pytest.raises(TypeError, match='immutable'):
            Parent()


def test_inherited_post_init_and_overridden_constraints():
    calls = []

    @immutable
    class Parent:
        number: int = 1

        def __post_init__(self):
            calls.append(self.number)

    @immutable
    class Child(Parent):
        number: Annotated[int, Min(5)] = 5

    assert Child().number == 5
    with pytest.raises(SchemaValueError):
        Child(number=4)
    assert calls == [5, 4]
    assert Parent(number=4).number == 4


def test_nested_models_require_exact_declared_type():
    @immutable
    class Parent:
        child: Base

    with pytest.raises(SchemaTypeError):
        Parent(child=Derived())
    assert Parent(child=Base()).child.x == 1


def test_nested_tuple_error_keeps_complete_path():
    @immutable
    class Grid:
        values: tuple[tuple[Annotated[int, Min(0)], ...], ...]

    with pytest.raises(SchemaValueError) as error:
        Grid(values=((0,), (1, -1)))
    assert error.value.path == ('values', 1, 1)


def test_empty_tuples_and_optional_models():
    @immutable
    class Value:
        empty: tuple[()] = ()
        child: Exposure | None = None

    assert Value().empty == ()
    assert Value(child=Exposure()).child == Exposure()
    with pytest.raises(SchemaValueError):
        Value(empty=(1,))


@pytest.mark.parametrize('base', [int, float, str, tuple])
def test_scalar_and_tuple_subclasses_are_rejected(base):
    class Subclass(base):
        pass

    hint = tuple[int, ...] if base is tuple else base

    @immutable
    class Value:
        item: hint

    with pytest.raises(SchemaTypeError):
        Value(item=Subclass())


def test_identity_registry_does_not_depend_on_equality_or_hash():
    @immutable
    class Value:
        number: int

        def __eq__(self, other):
            raise AssertionError('equality must not be used for certification')

        def __hash__(self):
            raise AssertionError('hash must not be used for certification')

    @immutable
    class Parent:
        child: Value

    value = Value(number=1)
    assert Parent(child=value).child is value
    forged = object.__new__(Value)
    object.__setattr__(forged, 'number', 1)
    with pytest.raises(SchemaValueError):
        Parent(child=forged)


def test_collecting_equal_instance_does_not_revoke_another():
    first, second = Exposure(), Exposure()
    reference = weakref.ref(first)
    del first
    gc.collect()
    assert reference() is None
    assert Layer(name='Photo', effect=second).effect is second


@pytest.mark.parametrize('name', ['__new__', '__getattribute__', '__getattr__',
                                 '__copy__', '__deepcopy__', '__reduce__',
                                 '__reduce_ex__', '__getstate__', '__setstate__'])
def test_custom_protocol_hooks_are_rejected(name):
    cls = type('Custom', (), {name: lambda *args: None})
    with pytest.raises(TypeError, match=name):
        immutable(cls)


def test_unsupported_dataclass_fields_are_rejected_before_factory_execution():
    from dataclasses import InitVar

    calls = []
    for hint, default in ((InitVar[int], 0),
                          (int, field(init=False, default_factory=lambda: calls.append(1)))):
        cls = immutable(type('Invalid', (), {'__annotations__': {'item': hint}, 'item': default}))
        with pytest.raises(TypeError):
            cls()
    assert calls == []


def test_class_variables_are_not_instance_fields():
    from typing import ClassVar

    @immutable
    class Value:
        name: ClassVar[str] = 'Value'
        number: int = 1

    assert Value().name == 'Value'
    with pytest.raises(TypeError):
        Value(name='Other')


@given(st.lists(st.integers(), max_size=40))
def test_persistent_tree_edits_preserve_previous_versions(values):
    root = Node(value=0)
    snapshots = []
    for value in values:
        snapshots.append(root)
        root = replace(root, value=value, children=(root,))
    for old in reversed(snapshots):
        assert root.children[0] is old
        root = old
    assert root == Node(value=0)


@given(st.lists(st.one_of(st.integers(), st.booleans(), st.text()), max_size=15))
def test_variadic_tuple_validation_checks_every_value(values):
    @immutable
    class Values:
        items: tuple[int, ...]

    items = tuple(values)
    if all(type(value) is int for value in items):
        assert Values(items=items).items is items
    else:
        with pytest.raises(SchemaTypeError) as error:
            Values(items=items)
        assert error.value.path == ('items', next(
            index for index, value in enumerate(items) if type(value) is not int))
