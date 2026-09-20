import types
from dataclasses import FrozenInstanceError, InitVar, dataclass, field, fields
from datetime import date, time
from functools import wraps
from typing import Literal, TypeVar, Union, dataclass_transform, get_args, get_origin, get_type_hints
from weakref import WeakValueDictionary

from pytypehint.bridge import _field_of, _split_annotated
from pytypehint.errors import SchemaTypeError, SchemaValueError, _prefixed
from pytypehint.shapes import Shape
from pytypehint.utils import MISSING


T = TypeVar("T")
_models: dict[type, "_Instance"] = {}
_scalars = (int, float, bool, str, date, time, type(None))


class _Instance(Shape):
    discriminator = "struct"

    def __init__(self, cls):
        self.cls = cls
        self.fields = None
        self.live: WeakValueDictionary = WeakValueDictionary()
        self.building: set[int] = set()

    @property
    def pytype(self) -> type:  # type: ignore[override]
        return self.cls

    def _check(self, value):
        if type(value) is not self.cls:
            raise SchemaTypeError(f"expected {self.cls.__name__}, got {type(value).__name__}")
        if self.live.get(id(value)) is not value:
            raise SchemaValueError("expected a successfully constructed @immutable instance")


def _dependencies(hint):
    base, _ = _split_annotated(hint)
    origin = get_origin(base)
    if origin in (Union, types.UnionType, tuple):
        for item in get_args(base):
            if item is not Ellipsis:
                yield from _dependencies(item)
    elif origin is Literal or base is None or base in _scalars:
        return
    elif isinstance(base, type) and base in _models:
        yield _models[base]
    else:
        raise TypeError(f"@immutable fields require immutable scalars, tuples or @immutable classes; got {base!r}")


def _compile(model, pending):
    if model.fields is not None or model.cls in pending:
        return
    pending[model.cls] = ()
    hints = get_type_hints(model.cls, include_extras=True)
    for name, hint in hints.items():
        if isinstance(hint, InitVar):
            raise TypeError(f"{name}: InitVar fields are not supported")
    compiled, dependencies = [], []
    # Opaque instance shapes reuse existing tuple, union and scalar validation.
    cache = dict(_models)
    for item in fields(model.cls):
        try:
            if not item.init:
                raise TypeError("init=False fields are not supported")
            dependencies.extend(_dependencies(hints[item.name]))
            compiled.append(_field_of(item.name, hints[item.name], MISSING, cache))
        except (TypeError, ValueError) as error:
            raise _prefixed(error, (item.name,)) from error
    pending[model.cls] = tuple(compiled)
    for dependency in dependencies:
        _compile(dependency, pending)


def _restore(cls, values):
    return cls(**values)


def _copy(self):
    _models[type(self)]._check(self)
    return self


def _deepcopy(self, memo):
    _copy(self)
    memo[id(self)] = self
    return self


def _reduce(self, protocol):
    _copy(self)
    return _restore, (type(self), {item.name: getattr(self, item.name) for item in fields(self)})


@dataclass_transform(frozen_default=True, kw_only_default=True, field_specifiers=(field,))
def immutable(cls: type[T]) -> type[T]:
    if not isinstance(cls, type):
        raise TypeError("immutable requires a class")
    if "__dataclass_fields__" in cls.__dict__:
        raise TypeError("use @immutable instead of @dataclass, not both")
    if any(base is not object and base not in _models for base in cls.__bases__):
        raise TypeError("@immutable bases must also use @immutable")
    for name in ("__init__", "__new__", "__getattribute__", "__getattr__",
                 "__copy__", "__deepcopy__", "__reduce__", "__reduce_ex__", "__getstate__", "__setstate__"):
        if name in cls.__dict__:
            raise TypeError(f"@immutable does not support custom {name}")

    model = dataclass(cls, frozen=True, slots=True, kw_only=True, weakref_slot=True)
    delattr(model, "__setstate__")
    initialize = model.__init__
    contract = _Instance(model)
    _models[model] = contract

    @wraps(initialize)
    def checked_init(self, *args, **kwargs):
        if type(self) is not model:
            raise SchemaTypeError("subclasses must also use @immutable")
        if id(self) in contract.building or contract.live.get(id(self)) is self:
            raise FrozenInstanceError("cannot reinitialize an immutable instance")
        if contract.fields is None:
            pending: dict = {}
            _compile(contract, pending)
            for kind, compiled in pending.items():
                _models[kind].fields = compiled
        contract.building.add(id(self))
        try:
            initialize(self, *args, **kwargs)
            for item in contract.fields:
                try:
                    item._check_value(getattr(self, item.name))
                except (TypeError, ValueError) as error:
                    raise _prefixed(error, (item.name,)) from error
            contract.live[id(self)] = self
        finally:
            contract.building.remove(id(self))

    setattr(model, "__init__", checked_init)
    setattr(model, "__copy__", _copy)
    setattr(model, "__deepcopy__", _deepcopy)
    setattr(model, "__reduce_ex__", _reduce)
    return model
