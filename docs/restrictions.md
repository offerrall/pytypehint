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

## Duplicate discriminator name

```text
Field 'x': duplicate discriminator name(s): Same
Field 'x': duplicate discriminator name(s): str
List.item: duplicate discriminator name(s): Same
```

There are two discriminators and therefore two namespaces. A dataclass names
itself with an inline `$type` among the other dataclasses; everything else names
itself inside the wrapper. Within one namespace an identity must belong to one
option.

Where a discriminator is in play, the reason is immediate: it would have nothing
left to name, and one of the two options would be unreachable. Where none is —
`int` beside an enum class named `int` routes perfectly well by exact Python
type — the identity is still the option's public name, the one that appears in
`Shape.option_id()`, in the document `to_dict` writes, and in the report that
lists what a field accepts. Two options answering to one name make all three
ambiguous for every reader, so the rule holds either way and is checked once.

The first message is the familiar case: two different classes called `Same` as
options of one field. The second is the same defect reached from further away —
an identity is spelled from the compiled shape, so options of unrelated kinds can
arrive at one. An enum class named `str` beside a `str`, one named `date` beside
a `date`, one named `list[str]` beside a `list[str]`: each pair leaves two options
answering to a single `$type`, and one of them would be unreachable.

The rule is about a namespace, not about a kind of option. A dataclass names
itself among the dataclasses and everything else names itself in the wrapper, so a
dataclass never competes for an identity with an option of another kind: an enum
and a dataclass of one class name are admissible together, and so is a dataclass
whose `__name__` is `"str"` beside a `str` — both options publish `"id": "str"`,
and both branches route and build, because routing is by exact runtime type. A
reader is expected to index the options of a slot by position and read an `id`
only to fill a discriminator, which is what [contract.md](contract.md) asks of it.
Within one namespace nothing is relaxed: two options may not share an identity,
and compilation rejects the pair.

The third message is the rule applied where the collision actually sits. A list's
items are what its elements name themselves by, and `List` is public API that can
be built directly, so a list refuses two items of one identity on its own rather
than waiting for a field to be built around it. That is why `list[Same | Same]`
is reported against `List.item` and not against the field carrying it: the shape
holding the two identities is refused wherever it is built, and a field is only
one of the places it can be built. Errors raised while a shape is being
constructed name the shape, as they do everywhere else.

Options that share a runtime type *and* an identity are reported as duplicate
option types instead, below — the same defect, named on its own terms.

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

## Sub-second `time`

```text
value: time precision is limited to whole seconds: 12:30:00.500000
Time.min: time precision is limited to whole seconds, got 12:30:00.500000
Time.choices: time precision is limited to whole seconds, got 12:30:00.500000
```

`Time` admits a value only when its `microsecond` is zero. Sub-second precision
carries no meaning in this domain, so a bound, a choice or a value that supplies
one is rejected — a bound or choice at compile time, a value wherever it is
validated (direct check, default certification, `resolve`, `build`, and inside
nested dataclasses, unions and lists). The effective range is therefore
`00:00:00..23:59:59`.

## Exclusive bound at a temporal edge

```text
Time: exclusive bound at 23:59:59 leaves no valid time
Time: exclusive bound at 00:00:00 leaves no valid time
```

An exclusive `Min` at the top of the range, or an exclusive `Max` at the bottom,
excludes the only value on that side of the bound and leaves the field
unsatisfiable. For `Date` the edges are `date.max`/`date.min`; for `Time`, with
its whole-second precision, they are `23:59:59`/`00:00:00`. Both reject the case
at compile time, symmetrically. The analogous `Float` edge
(`sys.float_info.max`) is deliberately left to run: it falls under the "no
general satisfiability" doctrine of [philosophy.md](philosophy.md), where the
core proves only the contradictions it can determine exactly.

## Non-finite float

```text
value: not finite: nan
```

NaN and infinity do not obey ordinary finite range semantics.

## A numeric atom that names no float

```text
Step.value must be finite, got inf
Float.step: expected int or float, got str
Float.min: must be finite, got inf
Float.choices: must be finite, got inf
```

The same rule, one step earlier: a bound, a choice and a step are all written into
the document as numbers a float reader will use, so none of them has a reading
outside the finite floats. `nan` slips past a `> 0` test by being neither positive
nor negative, `inf` passes it while naming no step at all, and both would reach
the portable tree as `NaN`/`Infinity`, which no JSON reader accepts — a `nan` also
makes a shape compare unequal to an identically written one. `Float` therefore
asks of its step exactly what `Int` asks of its own: a number, and a finite one.

An integer too large to convert (`10**400`) fails the same finiteness check, and
for the same reason: it names no float, so it is not a float bound. The integers
that *do* name a float, including the ones above `2**53` that name a neighbour
rather than themselves, are accepted and written as they stand — see
[contract.md](contract.md).

## File name that does not meet a `FileHint` contract

```text
not an accepted file type: 'image.gif', expected one of ('.png', '.jpg')
```

That is the whole list, and the reason it is one line long is the reason the atom
exists. `FileHint` states a file's contract — its accepted suffixes and its size
bounds — and the core checks the part of that contract the value can answer by
itself. The extension is spelled in the string, so the core settles it; existence
and size need a filesystem, a working directory and a moment in time, so the core
states them in the document and the wrapper applies them where it holds the file.
An answer obtained here would only have been true in this process at this instant,
and would have made a compiled schema depend on what happened to be on disk; see
[atoms.md](atoms.md).

Validation runs in one order: the value is exactly `str`, the ordinary `Str`
limits apply to the text, then the pattern, then the extension, and finally
`Choices`. The extension comes after the cheaper text rules and before `Choices`
because a value that is not even the right kind of file name should be named as
that, not as a missing choice.

The validated value is the same `str` that arrived. Nothing is coerced to
`pathlib.Path`, normalized, resolved, expanded or made absolute — the core never
constructs a path from it at all — so a relative name keeps its meaning for
whoever eventually opens it. Defaults and `Choices` are certified against the
extension when the schema compiles, with the field's coordinates in front:

```text
document: not an accepted file type: 'notes.txt', expected one of ('.pdf',)
files: [1]: not an accepted file type: 'image.gif', expected one of ('.png',)
Str.choices: not an accepted file type: 'default.txt', expected one of ('.png',)
```

## Invalid default

```text
n: default: expected int, got str
leaf: n: default: too large: 2, maximum 1
```

A default that violates its own schema is reported with `"default"` as a path
segment, the field's coordinates in front, and the violation as the leaf. One
format covers both moments the same defect can surface: certification at compile
time (the first line, from `struct_of`/`signature_of`) and per-serving
rematerialization at runtime (the second, from `build`/`resolve`). Purity and
determinism are the author's promise — per-serving validation reports observable
drift; other side effects cannot be diagnosed. See [defaults.md](defaults.md).

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

The error propagates raw, from `decode` as from `resolve` and `build`. Tracking
visited containers on every call would charge all real inputs for a cycle that
ordinary serialized data cannot contain — a portable tree parsed from a document
never holds one, and a hand-built dictionary that does is a program error rather
than an input error. Very deeply nested data reaches the interpreter's recursion
limit the same way, and the core does not impose a shallower limit of its own.

## A union option unreachable from a portable tree

Not an error, and worth knowing. `resolve` and `build` route by exact Python
type, so `str | date` is unambiguous to them. A portable tree spells both as
text, so a bare string can only be read as the `str`, and the `date` needs the
wrapper of [decode.md](decode.md) to be named:

```python
{"when": {"$type": "date", "$value": "2026-08-08"}}
```

The same holds for `int | float` on a whole number, and for any union mixing
`str`, `date`, `time` and enums. Where no option can take the bare spelling —
`date | time`, two enums — the bare value fails loudly instead, and the wrapper
is the only form that works.

If the alternatives are genuinely exclusive, the standard way out applies here
too: give each one a dataclass and route with `$type`.
