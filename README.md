# pytypehint 1.2.0

[![PyPI](https://img.shields.io/pypi/v/pytypehint.svg)](https://pypi.org/project/pytypehint/)

Define data with Python type hints. Validate input, build nested dataclasses,
inspect their fields or export a portable schema.

Use **`@immutable`** for deeply immutable models that validate themselves and
reuse validated children without checking their contents again.

Exact types, no implicit coercion. Python 3.11+, standard library only.
The schema and validation core of [FuncToWeb](https://github.com/offerrall/FuncToWeb).

```bash
pip install pytypehint
```

## Validate input into ordinary dataclasses

```python
from dataclasses import dataclass
from typing import Annotated
from pytypehint import Min, struct_of

@dataclass
class Item:
    name: str
    quantity: Annotated[int, Min(1)] = 1

schema = struct_of(Item)
item = schema.build({"name": "Pen"})  # Item(name='Pen', quantity=1)
schema.build({"name": "Pen", "quantity": 0})  # SchemaValueError: quantity
```

Compile once and reuse. Errors include the failing field or index in their `path`.

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
Exposure(stops="1.5")                      # SchemaTypeError
original.size = (800, 600)                  # FrozenInstanceError
```

Allowed fields are immutable scalars, tuples and other `@immutable` models.
Mutable containers, ordinary dataclasses and enums are rejected. The guarantee
covers declared fields through normal Python use; deliberate low-level mutation
can bypass it. [Full contract, inheritance and defaults](docs/immutable.md).

## Load portable data and inspect the same definition

The models above also work with the existing schema API:

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

| Method | Result |
|---|---|
| `build(data)` | Dataclass instance; `signature_of(fn)` returns kwargs for `fn(**kwargs)` |
| `resolve(data)` | Validated dictionary with missing defaults filled at this level |
| `decode(data)` | Portable values restored to Python types |
| `to_dict()` | Portable schema description |

## Documentation

- [Immutable models](docs/immutable.md)
- [Types and API](docs/vocabulary.md)
- [Atoms](docs/atoms.md)
- [Build](docs/build.md)
- [Resolve](docs/resolve.md)
- [Decode](docs/decode.md)
- [Tuples](docs/tuples.md)
- [Defaults](docs/defaults.md)
- [Portable contract](docs/contract.md)
- [Restrictions](docs/restrictions.md)
- [Guarantees](docs/guarantees.md)
- [Design](docs/philosophy.md)
- [Comparison](docs/comparison.md)
- [Changelog](CHANGELOG.md)
