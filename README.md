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

- [Overview](docs/overview.md): immutable models, portable data, field metadata and the four operations.
- [Immutable models](docs/immutable.md): the `@immutable` contract, allowed fields, reuse and Python behavior.
- [Types and API](docs/vocabulary.md): which hints compile to which shapes, and the public API.
- [Atoms](docs/atoms.md): constraints and notation per shape, file names, layering and extras.
- [Build](docs/build.md): validating and constructing instances or keyword arguments, union selection and errors.
- [Resolve](docs/resolve.md): validated dictionaries with defaults filled at the current level.
- [Decode](docs/decode.md): restoring portable values such as dates, enums and tuples before validation.
- [Tuples](docs/tuples.md): fixed, variadic and empty tuples and the `Tuple` shape.
- [Defaults](docs/defaults.md): certification and rematerialization of default values.
- [Portable contract](docs/contract.md): the JSON-compatible schema document returned by `to_dict()`.
- [Limits](docs/limits.md): rejected definitions, option identity and runtime limits.
- [Design](docs/design.md): what the core owns, what consumers own, and why.
