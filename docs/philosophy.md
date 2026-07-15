# Design principles

## Validate what the core can validate well

The core accepts the full vocabulary even when a UI cannot render it. Nested
lists and unions remain valid schemas; presentation belongs to the wrapper.
`Signature.build` prepares keyword arguments but never executes the function.

## `build` is a one-way boundary

External data enters as dictionaries and lists; constructed dataclasses leave.
A dictionary in a dataclass union uses `$type` because it carries no Python type.
Defaults belong to the author and may be instances; input may not. The core
constructs values, while the caller decides how to use or execute them.

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
