# Tuples

| Hint | Accepted value |
|---|---|
| `tuple[int, str]` | `(3, "red")` |
| `tuple[int]` | `(3,)` |
| `tuple[float, ...]` | Any number of exact floats |
| `tuple[()]` | `()` only |

`typing.Tuple[...]` supports the same forms. Bare tuples, unpacked hints and
slots containing only `None` are rejected. `tuple[int | None, ...]` is valid.
Positions may contain nested dataclasses, sequences, unions and type atoms.

```python
from dataclasses import dataclass
from typing import Annotated
from pytypehint import Max, Min, struct_of

Channel = Annotated[float, Min(0.0), Max(1.0)]

@dataclass
class Swatch:
    color: tuple[Channel, Channel, Channel, Channel]
    samples: Annotated[tuple[float, ...], Min(1), Max(16)]

schema = struct_of(Swatch)
value = schema.build({"color": (0.2, 0.8, 0.4, 1.0), "samples": (0.5,)})
```

Tuple-level `Min` and `Max` bound length with nonnegative integers, inclusive
only. Bounds excluding a fixed tuple's size fail at compilation. `Extra` is
supported; field atoms cannot apply to positions. Validation requires exact
tuples, checks length before contents and reports failing indexes.

Portable arrays become tuples through [decode](decode.md). Actual Python tuples
are left untouched, including their contents. Multiple tuple variants require
`{"$type": "tuple[int]", "$value": (3,)}` for Python input, or an array payload
for portable input. For `list[int] | tuple[int, ...]`, a bare portable array stays
a list; name the tuple option to restore it.

The public `Tuple` shape uses `items`, a tuple of option tuples, and `variadic`:

```python
from pytypehint import Int, Str, Tuple

pair = Tuple(items=((Int(),), (Str(),)))
sequence = Tuple(items=((Int(),),), variadic=True)
empty = Tuple(items=())
```

Fixed shapes have one slot per position; variadic shapes have one repeated slot.
`min`, `max` and `extras` describe the whole tuple. The [portable contract](contract.md)
uses `items` for fixed positions and `item` for repeated items. Tuple defaults
serialize as arrays and rematerialize their contents at each serving.
