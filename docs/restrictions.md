# Restrictions

Each restriction keeps the schema exact, inspectable or constructible.

## Input dataclass instance

```text
page: expected dict, got Page instance
```

Input is data until `build` crosses the construction boundary. Defaults may be
instances because they are authored recipes, not external input.

## Unsupported type

```text
unsupported type: <class 'complex'>
```

The vocabulary is closed so wrappers can inspect every possible shape.

## Bare list

```text
list requires an item type: list[X]
```

Without an item hint the core cannot validate list contents.

## Bare `None`

```text
Field 'x': None must be accompanied by another option
```

`None` expresses optionality; it needs a real value option.

## Option identity

A union routes an incoming value by its exact outer type. When two options share
that type, the value alone cannot select one, and the caller names it. The name
is the option's identity: a stable, readable string the core derives from the
compiled shape, never from `repr()`.

| Shape | Identity |
|---|---|
| scalar | its type name: `int`, `float`, `str`, `bool`, `date`, `time` |
| `NoneShape` | `None` |
| enum, dataclass | the class name: `Role`, `Fast` |
| `List` | its items spelled out: `list[str]`, `list[int \| None]`, `list[list[str]]` |

`Shape.option_id()` returns it. Dataclass options use it as `$type` inline;
everything else uses it inside the wrapper of [build.md](build.md).

## Duplicate option types in a union

```text
Field 'x': duplicate option types in shape
List.item has duplicate option types
```

Two options may share a runtime type — that is what the discriminator is for.
They may not also share an identity, because then there is nothing left to name.

`Literal` counts as its base type, so `Literal["a", "b"] | str` collides: both
compile to `Str` and both are identified as `str`. So does
`Annotated[int, Min(0)] | Annotated[int, Max(9)]` — atoms narrow a type, they do
not create one — and so does
`list[Annotated[int, Min(0)]] | list[Annotated[int, Max(9)]]`, one level down.

The core does not resolve such a pair by reading the value. Given `[]`,
`list[int] | list[str]` has no answer in the data, and both answers are wrong
half the time; given `[1, 2]` the answer is only in the contents, and reading
them would trade the exact error coordinates of [build.md](build.md) for a
heuristic that is confident and sometimes wrong. So the caller supplies the
answer, or there is no answer at all.

Ways out of a real collision. Mixed items that are genuinely one field become one
option: `list[int | str]`. Alternatives that are genuinely exclusive become
dataclasses and route by name with `$type`:

```python
from dataclasses import dataclass

@dataclass
class Fast: budget: int

@dataclass
class Safe: budget: int

mode: Fast | Safe   # {"$type": "Fast", "budget": 1}
```

Inside a list, where the author sees hints rather than compiled shapes, the
collision names both options and the way out:

```text
list items: Literal['a', 'b'] and str both compile to str — merge them into one option, or give each variant a dataclass and route with $type
```

## Variadic parameter

```text
args: variadic parameters (*args/**kwargs) are not supported
```

The input contract is named keyword data. Variadics have no fixed field schema.

## Positional-only parameter

```text
x: positional-only parameters are not supported
```

`Signature.build` returns keyword arguments, so it cannot represent a
positional-only call.

## Missing hint

```text
x: missing type hint
```

Every input field requires a schema.

## Lambda

```text
lambdas have no usable name; use a named function
```

`Signature.name` is inspectable wrapper metadata and must be meaningful.

## Callable other than a plain function

```text
expected a plain function, got <bound method Service.run of service> — bound methods, partials and callable objects are not supported: wrap the call in a plain function (def run(q: str): return service.search(q))
```

Bound methods, partials and callable objects hide binding state. Wrap them in a
plain named function. All plain function kinds compile normally; execution
policy belongs to the caller.

## Dataclass `InitVar` or `init=False`

```text
x: InitVar fields are not supported
x: init=False fields are not supported
```

A schema field must both enter the constructor and remain on the instance.

## Field atoms inside list items

```text
field atoms cannot apply to list items
```

List items have type constraints but no independent field presentation.

## Un-namespaced `Extra` key

```text
Extra.key must be namespaced ('package.name'), got 'color'
Extra.key must not be empty
Extra.key must be str, got int
Extra.value must be str, got int
```

An `Extra` key is the coordinate of a value the core stores and never reads, so
provenance is the only thing it can enforce: the dot names the owning package,
and several wrappers annotating one field stay out of each other's way. Beyond
its type the value is unconstrained — an empty value is legal, and what it means
belongs to the wrapper that wrote it.

## Hand-built extras that are not a mapping

```text
Int._extras must not repeat keys
Int._extras must be tuple, got dict
Int._extras: expected a (key, value) pair of str, got 'a.x'
```

Compilation merges extras by key, where a repeat is layering and the outer atom
wins. A shape constructed directly has no layers to resolve: its pairs are a
mapping, and a repeated key is a broken one. Storage is a sorted tuple, not a
dict, because the shapes are frozen and hashable and their equality must not
depend on the order the atoms were written in; `extras` rebuilds the dict on
access.

## `datetime`

```text
unsupported type: <class 'datetime.datetime'>
```

`date` and naive `time` have separate shapes. A combined timestamp would need
timezone and serialization policy that the core does not define.

## Flag enum

```text
EnumShape.cls: Flag enums are not supported (OR-combinable, not a closed set)
```

Flags combine members with bitwise OR, so their runtime value set is not the
closed choice set wrappers require.

## Enum without members

```text
EnumShape.cls: enum has no members
```

An empty enum provides no satisfiable value.

## Aware `time`

```text
value: must be naive (no tzinfo): 12:00:00+00:00
```

Comparing aware times requires date and timezone context. The `Time` shape is
explicitly naive.

## Non-finite float

```text
value: not finite: nan
```

NaN and infinity do not obey ordinary finite range semantics.

## Impure default

```text
leaf: n: default: too large: 2, maximum 1
```

Purity and determinism are the author's promise. Per-serving validation reports
observable drift; other side effects cannot be diagnosed. See
[defaults.md](defaults.md).

## Unhinted `self` or `cls`

```text
self: looks like an unbound method — pytypehint takes plain functions; wrap the call (def run(q: str): return service.search(q))
```

An unhinted leading receiver indicates an unbound method, not a standalone input
parameter. Wrap the bound operation in a plain function.

## Cyclic input data

```text
RecursionError: maximum recursion depth exceeded
```

The error propagates raw. Tracking visited containers on every call would charge
all real inputs for a cycle that ordinary serialized data cannot contain.
