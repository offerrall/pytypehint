# Design principles

## Validate what the core can validate well

The core accepts the full vocabulary even when a UI cannot render it. Nested
lists and unions remain valid schemas; presentation belongs to the wrapper.
`Signature.build` prepares keyword arguments but never executes the function.

## `build` is a one-way boundary

External data enters as dictionaries and lists; constructed dataclasses leave.
A dictionary in a dataclass union uses `$type` because it carries no Python type;
options that share a runtime type move into a `$type`/`$value` wrapper for the
same reason, since the type they arrive as names more than one of them.
Defaults belong to the author and may be instances; input may not. The core
constructs values, while the caller decides how to use or execute them.

## Restrict as little of Python as possible

Standard Python is the source of truth. A valid annotation that can be
represented strictly and unambiguously is admitted, even when routing it takes
more than the value itself.

`list[str] | list[int]` is such an annotation. Python allows it, and it means
something different from `list[str | int]`. The core once rejected it for a
reason that was about the core, not about the hint: both options arrive as a
`list`, so `type(value)` cannot pick one. That is a missing piece of
information, not an invalid type.

When a value carries enough information to select an option, the core selects
it and asks the caller for nothing. When it does not, the caller supplies the
selection explicitly — `{"$type": ..., "$value": ...}` — and the core still
never guesses. It does not read the contents of a list to infer an option, does
not try options in order, and does not accept the first one that happens to
validate: those would trade one exact answer for a heuristic that is confident
and sometimes wrong. Either the input determines the option or the caller names
it.

A default is the one place where no caller can name anything: it is a real
Python object authored in the schema, not input data. There the union means what
it means in Python — the value inhabits at least one option — and
rematerialization is identical through any option it inhabits, because each
element is rebuilt by its own exact type. The choice is an outcome, not a guess.

## A compiled schema is valid

Contradictory bounds, invalid atom combinations and invalid defaults fail during
`struct_of` or `signature_of`. Runtime validation starts from a schema whose
atoms are valid for their shapes and whose certified defaults satisfy every
applicable constraint.

Compilation rejects contradictions it can determine exactly. It does not prove
that every combination of constraints accepts at least one runtime value. For
example, a valid regular expression and valid length bounds may together accept
no string; without a default or explicit choices, that remains a valid schema
whose values will be decided by runtime validation.

## Validation fails fast

The first violation is reported and validation stops. There is no error list: a
schema error carries one coordinate and one reason, and
`SchemaTypeError`/`SchemaValueError` expose them as `path` and `leaf`.

Accumulating every error in a tree is presentation policy, and it belongs to the
wrapper that knows what it is presenting to. A form wants every field at once; a
CLI wants the first problem and an exit code; a queue consumer wants neither.
The wrapper holds the compiled schema, so it can walk the fields itself and
collect as many failures as it wants. Building that choice into the core would
charge the callers who never needed it.

## Hints are exact

`int` accepts values whose type is exactly `int`, not `bool`, a subclass or a
numeric string. Coercion is wrapper policy and stays visible at that boundary.
The vocabulary is closed: each restriction exists because accepting that case
would break an advertised guarantee.

## Defaults are recipes

A default is certified once, then rematerialized whenever its key is missing.
Lists and dataclass instances are fresh per build.

Two promises the core cannot prove belong to the author: recipes are pure, and
the input is not mutated while `build` constructs from it. Both are the same
trade: proving either would charge every honest call for a guard against a
mistake it did not make. An impure recipe and a constructor that edits its own
input remain the author's error.

## Schemas have identity

`Struct`, `Field` and `Signature` use identity equality. Compile once and share
the reference; two calls to `struct_of(Config)` produce distinct objects.
Recursive references reuse the root `Struct` object.

## Keep the public surface small

Every export must serve standalone validation or schema-driven wrappers.
Publishing less is cheap to correct; publishing implementation machinery creates
permanent compatibility obligations.

The core exposes structure, not convenience. A helper like "is this field
optional" cannot avoid taking a position: does it mean a `NoneShape` among the
options, a default that fills the missing key, or both? Consumers answer that
differently and are each right. A form treats a defaulted field as pre-filled
and still required; a patch endpoint treats it as omittable and reads the
default only to display it; a validator of raw payloads cares about
`NoneShape` alone. Raw structure does not opine, so all three read the field
and reach their own conclusion. A helper would have to choose one reading and
be wrong for the others, in the one place where being wrong is permanent.

Interpretation belongs to the layer that knows what it is asking for. Where
that interpretation is shared across wrappers it is worth writing once, but
the place for it is an intermediate package that depends on the core and
versions its own ergonomics separately — `pytypehint-inspect` and its like.
The core is what such a package reads, not where it lives. Proposals to add
interpretive helpers here — optionality, flattening, traversal, "the real
option of an `X | None`" — are answered by these two paragraphs.

## Expanding the vocabulary

The atom vocabulary is closed and curated. An atom describes one field: its
type, its limits, how that single control presents itself. It never describes
layout, grouping, or a relation between fields — where a field sits, which
fields travel together, which one enables another. Those are statements about a
form, not about a field, and they belong to the wrapper that renders the form or
to an intermediate package that models one.

The bar for admission is convergence. A new core atom must have semantics that
several rendering contexts agree on — a form, a CLI, a TUI each read it and
reach the same meaning — and it enters because that agreement already exists,
not because one wrapper needs somewhere to put a value. Every atom the core
names is a promise it maintains for every consumer, including the ones that will
never render it.

Everything else travels through `Extra`. An intermediate package defines its own
author-facing classes, typed and validated on its own terms, and compiles them
down to namespaced entries the core stores verbatim; its key names its owner, so
two packages annotate one field without meeting. The core stores coordinates,
never trees: it holds `str -> str` and reads neither side. A package that wants
structure serializes it inside its own value and parses it back — that keeps the
schema of the structure in the package that invented it, where it can version and
change without the core's permission.

The promotion path exists and runs one way. A convention proven in `Extra` across
wrappers may be promoted into the core vocabulary once its convergence is
demonstrated rather than argued. Nothing travels back: an atom the core has named
is a compatibility obligation, and demoting it would break every wrapper that
took the promise at face value.
