# Build

`Struct.build(data)` validates data and constructs a dataclass instance.
`Signature.build(data)` returns constructed keyword arguments; the caller invokes
or awaits the function.

```python
from dataclasses import dataclass
from pytypehint import signature_of, struct_of

@dataclass
class Config:
    count: int = 1

def run(config: Config):
    return config.count

config = struct_of(Config).build({"count": 2})
kwargs = signature_of(run).build({"config": {"count": 2}})
assert run(**kwargs) == 2
```

Input must be an exact `dict`, with exact Python values. Nested dataclasses take
dictionaries, not instances; lists and tuples keep their respective types.
Missing fields use [defaults](defaults.md); unknown or required missing keys fail.
For portable data, use `schema.build(schema.decode(data))`.

## Union selection

Different runtime types select themselves. Shared types need a discriminator;
contents and option order never select an input variant.

| Union | Input |
|---|---|
| `int \| str` | `3` or `"three"` |
| `A \| B` (dataclasses) | `{"$type": "A", ...fields...}` |
| `list[str] \| list[int]` | `{"$type": "list[str]", "$value": ["a"]}` |
| `tuple[int] \| tuple[str]` | `{"$type": "tuple[int]", "$value": (3,)}` |

Dataclass discriminators use the class name. Other wrappers use
`Shape.option_id()` and must contain exactly `$type` and `$value`.
Discriminators are accepted only where needed, including inside sequence items.
A lone dataclass rejects `$type` as an unexpected key. When dataclass and wrapped
options coexist, `$value` distinguishes the wrapper from a dataclass dictionary.
See [option identities](restrictions.md#option-identity).

`resolve` preserves validated discriminators; `build` removes them while
constructing the selected values. Defaults are Python values and need no wrapper.

## Errors and construction

Validation fails at the first error. `SchemaTypeError` and `SchemaValueError`
subclass `TypeError` and `ValueError` and expose `path` and `leaf`:

```text
cart: items: [0]: size: default: too large: 145, maximum 100
terms: $value: [1]: expected str, got int
```

Supplied input is validated before construction. Nested dictionaries become
instances, and lists and tuples are rebuilt with their constructed contents.
Missing defaults are served at their own depth. Constructor and `__post_init__`
exceptions propagate unchanged; use `__post_init__` for cross-field checks.
Do not mutate input during construction, including from a constructor: supplied
values are validated once and are not checked again after mutation.
