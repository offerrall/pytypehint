# Resolve

`Struct.resolve(data)` and `Signature.resolve(data)` validate field by field,
reject unknown or missing keys, and fill missing defaults with fresh values.
They return a dictionary and do not construct dataclass instances from nested
dictionaries.

Validation reaches every depth; filling does not. A supplied value is checked
all the way down — inside nested dictionaries, lists and unions — while defaults
are served only for the keys missing at the level being resolved. A nested
dataclass dictionary keeps exactly the keys it arrived with, and `build` fills
that dataclass's own missing defaults while constructing it. The example below
shows the shape of that split.

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
removes the discriminator when constructing the selected class. The same holds
for the `$type`/`$value` wrapper of [build.md](build.md): `resolve` returns the
wrapper as it was given, and `build` unwraps it. Input dataclass instances are
rejected by both APIs.

`resolve` expects exact Python, like `build`. A tree that arrived in a portable
form goes through [`decode`](decode.md) first; the two are separate calls, and
`resolve` never decodes anything on its own. A supplied value passes through
`resolve` by reference — it is validated, never transformed.
