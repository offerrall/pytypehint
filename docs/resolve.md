# Resolve

`Struct.resolve(data)` and `Signature.resolve(data)` validate field by field,
reject unknown or missing keys, and fill missing defaults with fresh values.
They return a dictionary and do not construct dataclass instances from nested
dictionaries.

```python
from dataclasses import dataclass, field
from pytypehint import struct_of

@dataclass
class Page:
    size: int = 20

@dataclass
class Query:
    page: Page = field(default_factory=Page)

resolved = struct_of(Query).resolve({"page": {"size": 50}})
# {'page': {'size': 50}}
```

Use `resolve` when a wrapper must inspect validated data before construction—for
example, to move an uploaded file or inject request context. Most standalone
callers should use `build`.

For a dataclass union, `resolve` validates `$type` and preserves it. `build`
removes the discriminator when constructing the selected class. Input dataclass
instances are rejected by both APIs.
