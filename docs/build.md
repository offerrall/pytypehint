# Build

`Struct.build(data)` returns a validated dataclass instance.
`Signature.build(data)` returns validated, constructed keyword arguments. It
never calls the function; use `fn(**kwargs)` or `await fn(**kwargs)` yourself.

```python
from dataclasses import dataclass
from pytypehint import signature_of, struct_of

@dataclass
class Config:
    n: int = 1

def run(config: Config):
    return config.n

data = {"n": 2}
instance = struct_of(Config).build(data)
kwargs = signature_of(run).build({"config": data})
result = run(**kwargs)
```

## Data in, objects out

Input uses dictionaries for every dataclass, including nested values. Instances
are rejected because input belongs to the external-data side of the boundary:

```text
page: expected dict, got Page instance
```

Defaults are authored schema data and may still be dataclass instances.

Nested dictionaries become instances; nested lists are rebuilt with their
contents constructed. Input values are validated by exact type before any
constructor runs.

## Dataclass unions and `$type`

Scalar union values already carry their Python type. A dictionary does not, so a
union containing two or more dataclasses requires the reserved `$type` key. Its
value is the selected class's `__name__`.

```python
from dataclasses import dataclass
from pytypehint import struct_of

@dataclass
class File: path: str

@dataclass
class Url: value: str

@dataclass
class Source: value: File | Url

data = {"value": {"$type": "Url", "value": "https://example.test"}}
struct_of(Source).resolve(data)
# {'value': {'$type': 'Url', 'value': 'https://example.test'}}
struct_of(Source).build(data)    # Source(value=Url(...)); consumes $type
```

Missing and invalid discriminators fail as follows:

```text
value: ambiguous dict: field accepts File | Url — add "$type" naming the variant
value: $type: not a choice: 'Other', expected one of ('File', 'Url')
value: $type: expected str, got int
```

`$type` on a non-ambiguous dataclass is an ordinary unexpected key. The name
cannot collide with a dataclass field because fields must be identifiers.
Discrimination works at every nesting depth and in union-valued list items.

## Other unions that share an input type: `$type` and `$value`

A dictionary has room for an inline `$type`; a list does not. When two options
that are not dataclasses arrive as the same runtime type, the value moves into a
wrapper that makes room for the discriminator:

```python
from dataclasses import dataclass
from pytypehint import struct_of

@dataclass
class Query:
    terms: list[str] | list[int]

data = {"terms": {"$type": "list[str]", "$value": ["a", "b"]}}
struct_of(Query).resolve(data)   # returns data unchanged
struct_of(Query).build(data)     # Query(terms=['a', 'b']); consumes the wrapper
```

`$type` is the option identity of [restrictions.md](restrictions.md) —
`list[str]`, `list[int]`, `list[list[str]]`. It selects one option, and only
then is `$value` validated against that option. The wrapper carries those two
keys and nothing else.

The wrapper is required exactly where routing is ambiguous, and accepted only
there. `int | str`, `list[str | int]` and `list[int] | None` route themselves by
exact type and take no discriminator; on them a wrapper is just a foreign
dictionary. Where a dataclass option sits beside ambiguous ones, the reserved
`$value` key tells the two dictionary formats apart.

Failures keep their coordinates, including `$value` and the index below it:

```text
terms: ambiguous list: field accepts list[str] | list[int] — wrap it as {"$type": ..., "$value": ...} naming the option
terms: $type: not a choice: 'list[float]', expected one of ('list[str]', 'list[int]')
terms: $type: expected str, got int
terms: missing key(s): $value
terms: unexpected key(s): note
terms: $value: [1]: expected str, got int
```

A default is a value, not input data: it is a real Python object that no caller
can wrap, so it needs no discriminator. `list[str] | list[int]` accepts
`default_factory=list`, and the empty list is served fresh per missing key like
any other.

## Errors and constructors

Validation errors accumulate field names and list indexes:

```text
cart: items: [0]: size: default: too large: 145, maximum 100
```

Nested `resolve` failures receive the complete path. Once validation succeeds,
`__init__` and `__post_init__` exceptions propagate unchanged: they are program
errors, not input-coordinate errors. Put cross-field validation in
`__post_init__`; it runs after each successful construction.

`build` validates the input tree once and then constructs from it. Do not mutate
the input while that construction is running: `__post_init__` is for cross-field
validation, not for effects on the input data. A constructor that reaches back
and edits the dictionaries still being built reads values the core has already
validated and will not check again, so the result is undefined. This is the same
promise [defaults.md](defaults.md) asks for recipes, and it belongs to the author
for the same reason: the core cannot prove it without charging every honest input
for the check.
