# pytypehint

Define data once with ordinary Python type hints and dataclasses. pytypehint
compiles them into strict schemas that validate input with exact types and no
implicit coercion, build nested dataclasses, and export a portable description
another process can read.

Use `@immutable` for deeply immutable models that validate themselves and reuse
already validated children. pytypehint is the schema and validation core of
[func-to-web](https://offerrall.github.io/func-to-web/).

```python
from dataclasses import dataclass
from typing import Annotated
from pytypehint import Min, struct_of

@dataclass
class Item:
    name: str
    quantity: Annotated[int, Min(1)] = 1

schema = struct_of(Item)
item = schema.build({"name": "Pen"})          # Item(name='Pen', quantity=1)
schema.build({"name": "Pen", "quantity": 0})  # SchemaValueError: quantity
```

The full documentation is at https://offerrall.github.io/pytypehint/.

## Documentation

- [Overview](https://offerrall.github.io/pytypehint/): immutable models, portable data, field metadata and the four operations.
- [Immutable models](https://offerrall.github.io/pytypehint/immutable/): the `@immutable` contract, allowed fields, reuse and Python behavior.
- [Types and API](https://offerrall.github.io/pytypehint/vocabulary/): which hints compile to which shapes, and the public API.
- [Atoms](https://offerrall.github.io/pytypehint/atoms/): constraints and notation per shape, file names, layering and extras.
- [Build](https://offerrall.github.io/pytypehint/build/): validating and constructing instances or keyword arguments, union selection and errors.
- [Resolve](https://offerrall.github.io/pytypehint/resolve/): validated dictionaries with defaults filled at the current level.
- [Decode](https://offerrall.github.io/pytypehint/decode/): restoring portable values such as dates, enums and tuples before validation.
- [Tuples](https://offerrall.github.io/pytypehint/tuples/): fixed, variadic and empty tuples and the `Tuple` shape.
- [Defaults](https://offerrall.github.io/pytypehint/defaults/): certification and rematerialization of default values.
- [Portable contract](https://offerrall.github.io/pytypehint/contract/): the JSON-compatible schema document returned by `to_dict()`.
- [Limits](https://offerrall.github.io/pytypehint/limits/): rejected definitions, option identity and runtime limits.
- [Design](https://offerrall.github.io/pytypehint/design/): what the core owns, what consumers own, and why.
