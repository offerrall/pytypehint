# Resolve

`Struct.resolve(data)` and `Signature.resolve(data)` return a new dictionary of
validated values, filling defaults for missing keys at the current level.
Unknown keys and missing required keys fail. Input must use exact Python types;
portable data goes through [decode](decode.md) first.

Supplied values are validated at every depth and retained by reference. Nested
dataclass dictionaries keep their original keys, and union discriminators stay
in place. `resolve` does not construct nested instances or expand their defaults;
[build](build.md) does that.

```python
from dataclasses import dataclass
from pytypehint import struct_of

@dataclass
class Page:
    size: int = 20

@dataclass
class Query:
    page: Page

schema = struct_of(Query)
assert schema.resolve({"page": {}}) == {"page": {}}
assert schema.build({"page": {}}) == Query(Page(size=20))
```

Use `resolve` to inspect validated data before construction. Use `build` when you
want the finished object. A default may itself construct an instance; see
[defaults](defaults.md).
