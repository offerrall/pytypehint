# pytypehint 1.1.0

[![PyPI](https://img.shields.io/pypi/v/pytypehint.svg)](https://pypi.org/project/pytypehint/)

Validate data and build ordinary dataclasses from Python type hints.
Supports nested models, lists, tuples, enums, unions and `Annotated` constraints.
Inspect the compiled schema or export it as portable data.
Types are exact: no implicit coercion. Python 3.11+, standard library only.

The schema and validation core of [FuncToWeb](https://github.com/offerrall/FuncToWeb).

```bash
pip install pytypehint
```

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
```

Compile once and reuse the schema. Invalid input raises `SchemaTypeError` or
`SchemaValueError`, with the failing field or index in the error path.

| Method | Result |
|---|---|
| `build(data)` | Dataclass instance; `signature_of(fn)` returns kwargs for `fn(**kwargs)` |
| `resolve(data)` | Validated dictionary with missing defaults filled at this level |
| `decode(data)` | Portable values restored to Python types |
| `to_dict()` | Portable schema description |

For portable input, use `schema.build(schema.decode(data))`.

## Documentation

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
