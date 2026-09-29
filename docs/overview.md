# Overview

pytypehint turns a dataclass or a function signature into a compiled schema:
`struct_of(Item)` returns a `Struct`, `signature_of(fn)` a `Signature`. Compile
once and reuse. Validation is exact: `float` rejects `int`, `int` rejects `bool`,
and nothing is coerced. The first error raises `SchemaTypeError` or
`SchemaValueError` with the failing field or index in its `path`.

## Immutable models

Declare constraints once. Normal construction and `dataclasses.replace` validate
automatically; nested instances keep their identity.

```python
from dataclasses import replace
from typing import Annotated
from pytypehint import Max, Min, immutable

Positive = Annotated[int, Min(1)]
Channel = Annotated[float, Min(0.0), Max(1.0)]

@immutable
class Exposure:
    stops: float = 0.0

@immutable
class Grayscale:
    pass

@immutable
class Layer:
    name: Annotated[str, Min(1)]
    effect: Exposure | Grayscale
    color: tuple[Channel, Channel, Channel, Channel] = (0.0, 0.0, 0.0, 1.0)

@immutable
class Document:
    size: tuple[Positive, Positive]
    layers: tuple[Layer, ...] = ()

photo = Layer(name="Photo", effect=Exposure(stops=1.5))
original = Document(size=(1920, 1080), layers=(photo,))
resized = replace(original, size=(3840, 2160))

assert resized.layers[0] is photo
assert original.size == (1920, 1080)
```

The new document checks its size and layer references, without revisiting the
existing layer's fields. Tuples are checked; existing immutable children are reused.

```python
replace(photo, color=(1.0, 0.0, 0.0, 2.0))  # SchemaValueError, path: ('color', 3)
Exposure(stops="1.5")                       # SchemaTypeError
original.size = (800, 600)                  # FrozenInstanceError
```

Fields are restricted to immutable scalars, tuples and other `@immutable` models;
see [Immutable models](immutable.md) for the full contract, inheritance and defaults.

## Portable data and inspection

The same models work with the schema API. `decode` restores portable values such
as JSON arrays and discriminated unions, and `to_dict` describes the schema for a
UI or another process:

```python
from pytypehint import struct_of

schema = struct_of(Document)
loaded = schema.build(schema.decode({
    "size": [1920, 1080],
    "layers": [{
        "name": "Photo",
        "effect": {"$type": "Exposure", "stops": 1.5},
    }],
}))

assert loaded == original
contract = schema.to_dict()  # Portable description for a UI or another process
```

Type constraints and interface metadata live on the same field:

```python
from pytypehint import Label, Slider, Step

@immutable
class Brush:
    size: Annotated[int, Min(1), Max(256), Label("Brush size"), Step(1), Slider()] = 32

size_field, = struct_of(Brush).fields
size_shape, = size_field.shape
assert size_field.label.value == "Brush size"
assert size_shape.max.value == 256
```

## The four operations

| Method | Result |
|---|---|
| [`build(data)`](build.md) | Dataclass instance; `signature_of(fn)` returns kwargs for `fn(**kwargs)` |
| [`resolve(data)`](resolve.md) | Validated dictionary with missing defaults filled at this level |
| [`decode(data)`](decode.md) | Portable values restored to Python types |
| [`to_dict()`](contract.md) | Portable schema description |
