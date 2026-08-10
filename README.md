# pytypehint 1.0.0

[![PyPI](https://img.shields.io/pypi/v/pytypehint.svg)](https://pypi.org/project/pytypehint/)

`pytypehint` compiles standard Python type hints into strict, inspectable,
portable contracts.

Your code remains ordinary Python:

* **No custom models, decorators, mutation, registration, or runtime hooks.**
* **Your dataclasses remain untouched and work without `pytypehint`.**
* **The library only observes them from the outside and compiles a separate schema.**

The dataclass is the single source of truth:

* types come from type hints;
* constraints and presentation come from `Annotated`;
* defaults are validated and rematerialized fresh;
* the contract can be exported as data, and data arriving in a portable form can
  be recovered into exact Python;
* plain input is validated and converted into dataclass instances.

**Standard Python in. A strict contract out — inspectable in memory, portable as data.**

Stdlib only. Python 3.11+. `py.typed` included.

```bash
pip install pytypehint
```

```python
from dataclasses import dataclass, field
from typing import Annotated
from pytypehint import Label, Max, Min, signature_of, struct_of

@dataclass(frozen=True)
class Page:
    number: Annotated[int, Min(1)] = 1
    size: Annotated[int, Min(1), Max(100), Label("Page size")] = 20

@dataclass
class Search:
    query: str
    page: Page = Page()
    tags: list[str] = field(default_factory=list)

value = struct_of(Search).build({"query": "python", "page": {"size": 50}})
# Search(query='python', page=Page(number=1, size=50), tags=[])

try:
    struct_of(Search).build({"query": "python", "page": {"size": 500}})
except ValueError as error:
    assert str(error) == "page: size: too large: 500, maximum 100"

def search(query: str, page: Page = Page()): ...
kwargs = signature_of(search).build({"query": "python"})
search(**kwargs)  # execution belongs to the caller
```

## The problem it solves

A type hint already describes what a value must be. Everything downstream —
validating a payload, constructing the object, rendering a form, generating a
client, storing a row — needs that description, and without a shared one each
consumer rebuilds it, slightly differently, and the differences are silent.

`pytypehint` compiles the hints once into a schema that is exact enough to
validate against, structured enough to inspect, and portable enough to hand to a
program written in another language. It stops there. What any of it should look
like, how it should be transported, and when it should run are decisions the core
does not make.

## The four operations

A compiled `Struct` or `Signature` answers four questions, and each is a separate
step so the boundary between them stays visible:

| Call | In | Out |
|---|---|---|
| `schema.to_dict()` | — | the contract as a portable tree |
| `schema.decode(data)` | portable tree | exact Python tree |
| `schema.resolve(data)` | exact Python tree | validated tree, defaults filled |
| `schema.build(data)` | exact Python tree | constructed instance / kwargs |

```python
from datetime import date

@dataclass
class User:
    name: str
    birthday: date

schema = struct_of(User)

schema.fields                          # inspect the contract in Python
contract = schema.to_dict()            # export it; json.dumps(contract) works

wire = {"name": "Ana", "birthday": "2000-05-17"}
prepared = schema.decode(wire)         # {'name': 'Ana', 'birthday': date(2000, 5, 17)}
schema.build(prepared)                 # User(name='Ana', birthday=date(2000, 5, 17))

schema.build(wire)                     # birthday: expected date, got str
```

That last line is the point of the design. `"2000-05-17"` is a `str`, and `build`
says so. `decode` is what turns it into a `date`, and only because the schema
says that field is a date.

### `decode` is not coercion

A portable tree carries `dict`, `list`, `str`, `int`, `float`, `bool` and `None`,
and nothing else. Three of the core's types have no carrier there and arrive
spelled as something else — a `date` and a `time` as text, an enum member as its
name — and one more can lose part of itself on the way out: a whole `float` may
arrive as `3` rather than `3.0`. `decode` restores those four. It does nothing
else, at any depth, under any schema:

```text
"3" ──▶ int      "true" ──▶ bool      "" ──▶ None      tuple ──▶ list
```

None of those happen. A `str` field holding `"2026-08-08"` stays a `str`, however
much it looks like a date — the shape decides the reading, and the text never
does. Where two options of a union share a portable spelling, nothing is decoded
and the caller names the option with the discriminator the core already has.
Coercion — reading `"12"` as `12` — is interface policy and lives in the wrapper
that knows what interface it is reading. See [decode.md](docs/decode.md).

The core never parses or emits JSON text. `json.loads` and `json.dumps` are the
caller's, and the same contract then serves a file, a queue, an RPC boundary or
another language:

```text
JSON text ──json.loads()──▶ portable tree ──decode()──▶ exact Python ──build()──▶ objects
```

## Guarantees

- Exact types: `type(value) is T`. `resolve` and `build` never convert anything,
  and `decode` only restores what a portable tree cannot carry.
- Data enters as dictionaries and lists; dataclass instances leave through `build`.
- A union routes by the exact runtime type of the value. Where two options share
  that type — `list[str] | list[int]`, `A | B` — the caller names one; the core
  never guesses from the contents, from the option order, or by trying them. The
  same rule governs `decode`, one level earlier, over the spellings a portable
  tree can carry.
- Two options of a union may share a runtime type, but never an identity: the
  discriminator has to have something to name.
- Defaults are certified at compilation and rematerialized per missing key.
  Immutable scalar values and enum members may be reused; lists and dataclass
  instances are reconstructed. A `default_factory` runs during certification
  and again whenever its missing value is served.
- Invalid atom combinations and contradictions the core can determine exactly
  fail while compiling the schema. The core does not attempt a general
  satisfiability proof across unrelated constraints.
- `FileHint` marks a `str` that names a file and carries that file's contract:
  the extensions it may take, and the sizes it must fall between. The core
  validates the extension, because the text of the value answers that question by
  itself, and it never consults the filesystem. Existence, regular-file status
  and the byte sizes are stated, travel in the portable document, and are checked
  at the wrapper's boundary — the upload, the command-line argument — which is
  the only place holding the file itself, and the only place where the answer is
  still true when the file is used. The value stays exactly `str` throughout.
  Defaults and `Choices` are certified under the same extension rule when the
  schema compiles.
- Errors retain the complete field and list-index path, as the message text and
  as data: `SchemaTypeError` and `SchemaValueError` carry `path` and `leaf`, and
  subclass `TypeError` and `ValueError`. `decode` raises neither: it prepares,
  and validation reports.
- Notation atoms are stored and cross-checked but never affect validation;
  presentation belongs to the wrapper.
- `Struct`, `Field` and `Signature` compare by identity; compile once and share.
- `build` validates supplied input values once and then constructs directly.
  Missing defaults are materialized and validated at their own depth.
- `resolve` validates the supplied tree at every depth and fills defaults for
  missing fields at the level being resolved. A supplied nested dataclass
  dictionary remains a dictionary and is not recursively expanded with that
  dataclass's defaults; `build` fills those defaults while constructing the
  nested instance.
- `decode` never modifies the tree it is given, and rebuilds every `dict` and
  `list` it descends into. A container a portable tree cannot carry — one reached
  through a tuple, or a `dict`/`list` subclass such as `OrderedDict` — is handed
  back as the same object, on purpose: rebuilding it as its base class would be
  the coercion the rule forbids. It fills no defaults, drops no unknown keys, and
  runs no recipes.
- `Struct.to_dict()` and `Signature.to_dict()` are deterministic — equal
  definitions produce equal documents, byte for byte, across processes and hash
  seeds — and return a fresh tree the caller owns. Nothing is cached.
- `Signature.build` returns constructed keyword arguments and never invokes the function.

## What it does not do

Coerce interface input, render controls, accumulate every failure in a tree,
interpret the schema on a consumer's behalf, parse or emit JSON text, execute
functions, or know anything about HTTP, browsers, HTML, CSS, command lines, Qt,
filesystems, databases or authentication.

That list has no exceptions in it. The core answers every question the schema and
the value can answer between them, and nothing that requires asking the world:
not the filesystem, not the network, not the environment, not the working
directory, not the clock. It describes what must hold and the wrapper verifies it
where it holds the thing being described — the reasoning is in
[philosophy.md](docs/philosophy.md), and the line it draws against other libraries
in [comparison.md](docs/comparison.md).

## Vocabulary

| Hint | Shape | Input |
|---|---|---|
| `int` | `Int` | exact `int` |
| `float` | `Float` | exact `float` |
| `str` | `Str` | exact `str` |
| `bool` | `Bool` | exact `bool` |
| `date` | `Date` | exact `datetime.date` |
| `time` | `Time` | exact naive `datetime.time` |
| `Enum` subclass | `EnumShape` | exact member type |
| `None` | `NoneShape` | `None` |
| `list[X]` | `List` | list; nesting and union items supported |
| dataclass | `Struct` | dictionary; `build` constructs it |
| `A \| B` | tuple of shapes | exact scalar type or routed dataclass dictionary |
| `list[str] \| list[int]` | tuple of shapes | `{"$type": "list[str]", "$value": [...]}` |
| `Literal[...]` | `Int` or `Str` with `Choices` | homogeneous `int` or `str` literals |

That list is closed by design and complete by a criterion: a type is a primitive
only when it has one reading and no policy attached, and one that needs a policy
to exist — `datetime`, which would force a choice of timezone, precision and
serialization — is written as a dataclass whose author fixes it. Composition is
where the room is, and it is unbounded, so the names stay this few while the
schemas they express do not. See [philosophy.md](docs/philosophy.md).

Python allows `list[str | int]` and `list[str] | list[int]`, and they mean
different things. The core keeps both, and asks for a discriminator only where
the value cannot supply one:

```python
mixed: list[str | int]          # {"mixed": ["a", 1, "b", 2]}
either: list[str] | list[int]   # {"either": {"$type": "list[str]", "$value": ["a", "b"]}}
```

Every element of `mixed` routes by its own exact type. `either` chooses one
option for the whole list, and both options arrive as a `list`, so the caller
names the one it meant. See [build.md](docs/build.md).

## Ecosystem

`pytypehint` is the policy-free contract core. A wrapper reads the same compiled
schema — in memory through `Struct` and `Field`, or as data through
`schema.to_dict()` — and adds exactly what its own environment needs:

* **[`pytypehintweb`](https://github.com/offerrall/pytypehintweb)** compiles schemas into a strict, expanded JSON plan and provides a framework-free browser runtime for rendering forms and transporting their values back to Python.
* **[`FuncToWeb`](https://github.com/offerrall/FuncToWeb)** exposes typed Python functions through generated web interfaces while leaving invocation, presentation and application policy outside the core.
* **[`pytypehintstore`](https://github.com/offerrall/pytypehintstore)** keeps rows of one validated dataclass in memory and mirrors them to a JSON file named after the class and the fingerprint of its compiled schema, so a changed contract is a separate database instead of a migration.

These packages build on `pytypehint`; they are not required to define, compile,
validate or construct models with the core library.

The portable contract exists because each of those had to learn the same thing
separately. A command line understands command lines, a browser understands
browsers, a store understands storage — and the core understands the contract, so
a wrapper that has not been written yet can consume it without reproducing its
semantics.

## Public API

Everything public is exported from `pytypehint`:

- `struct_of`, `signature_of`;
- `Struct`, `Field`, `Signature`;
- errors: `SchemaTypeError`, `SchemaValueError`;
- `Shape`, `Int`, `Float`, `Str`, `Bool`, `Date`, `Time`, `List`,
  `NoneShape`, `EnumShape`;
- limits: `Min`, `Max`, `Choices`, `MultipleOf`, `Pattern`, `FileHint`;
  `FileHint(extensions=(), min_size=None, max_size=None)` — sizes in bytes,
  declared for the boundary that has the file, not checked by the core;
- notation: `Label`, `Description`, `Placeholder`, `Step`, `Slider`,
  `IsPassword`, `Rows`, `Extra`, `OptionalToggle`;
- `MISSING`.

The four operations are methods on the compiled schema, not separate exports:
`.to_dict()`, `.decode(data)`, `.resolve(data)` and `.build(data)` on both
`Struct` and `Signature`.

A file input is a `str`, not a new type:

```python
FilePath = Annotated[
    str,
    FileHint(
        extensions=(".pdf",),
        max_size=10 * 1024 * 1024,
    ),
]
```

The core reads the extension out of the text and rejects `"report.txt"` here. The
ten megabytes are not a check it performs but a fact it publishes, so the wrapper
receiving the upload can refuse the file before it becomes anyone's problem.

`Extra(key, value)` takes a key containing a namespace separator
(`"package.name"`; a dot is required) and any string value, including an empty
string. A shape merges every `Extra` on its hint by key; the rightmost/outermost
value wins for a repeated key. Internally the pairs are sorted and immutable.
The `extras` property returns a fresh `dict[str, str]` on every access, so callers
may modify that snapshot without changing the shape. The core stores these
entries but never interprets them.

Start with [the design principles](docs/philosophy.md), then read
[build](docs/build.md), [resolve](docs/resolve.md), [decode](docs/decode.md),
[the portable contract](docs/contract.md), [defaults](docs/defaults.md),
[vocabulary](docs/vocabulary.md), [atoms](docs/atoms.md),
[restrictions](docs/restrictions.md), and [comparison](docs/comparison.md).
