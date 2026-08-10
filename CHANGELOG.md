# Changelog

## [1.0.0] - 2026-08-10

The core now owns the portable form of its own types. Until this release a
compiled schema could only be read as Python objects, in the process that
compiled it; every consumer that needed it elsewhere — a browser, a stored row,
another language — invented its own way to write the contract down and to read
values back, and the dialects diverged in ways nothing detected. Two operations
close that boundary, and the public surface grows by no new names: both are
methods on the schema that was already there.

Owning that boundary forced a second question, and answering it is the other half
of this release: what may the core check at all? The rule it now holds to is that
the core verifies everything the schema and the value can answer between them, and
nothing that requires asking the world — not the filesystem, not the network, not
the environment, not the working directory, not the clock. One atom broke that
rule, and a contract meant to be compared byte for byte cannot afford an answer
that changes with what happens to be on disk. So the rule comes first, and the
atom follows it.

What breaks is listed first, then `decode`, then the document `to_dict` writes,
then what validation and its errors guarantee.


- Breaking: `IsPathFile` is now `FileHint`, and the core no longer touches the
  filesystem. The atom keeps its three fields — `extensions`, `min_size`,
  `max_size` — and every cross-check between them; what it loses is the
  verification. `Str._check` validates the extension, which is spelled in the
  value and settled by the text alone, and states the sizes without testing them.
  The field on the shape is `Str.file_hint` and the document key is `"file_hint"`,
  with the contents unchanged. Gone with the `stat()` call are the errors
  `file does not exist`, `not a file`, `file too small`, `file too large` and
  `cannot inspect file`; `not an accepted file type` is the one that remains.

  This was the last place the core asked the world anything, and the rule it
  broke is now stated plainly: the core verifies everything the schema can
  answer, and nothing that requires asking outside the process. A fact about a
  file is only true where and when it is read. Checking existence at compilation
  proves nothing about the moment the value is used — the file can go in between,
  and a caller who saw the schema accept it has been given a promise the core
  cannot keep. The verification is real only at the boundary that has the file in
  hand, which is the upload, the command-line argument, the request — and that
  boundary is the wrapper, which is why the sizes travel in the document instead
  of being consumed here.

  It also cost the portable contract its central property. Which option a default
  inhabits was decided by asking the options what they accept, so with a
  world-reading atom in the slot the same definition wrote one document while a
  file existed and another after it was deleted, resolved a relative path against
  whatever directory the process happened to stand in, and could fail the emitter
  outright on a schema the core had accepted. The emitter carried a workaround for
  this — it stripped the atom before routing — and the workaround did not descend
  into a nested dataclass, so the leak stayed open at depth. Both the atom's check
  and the workaround are gone. `to_dict()` is now deterministic with no asterisk
  attached, and `README.md` can say the core knows nothing about filesystems and
  mean it literally.

  What is lost, stated plainly: a default naming a file that does not exist no
  longer fails at import. If an application wants that check, it is three lines at
  startup, over the defaults it already has, in the process that knows which
  directory they are relative to — which is where the answer was ever true. There
  is no deprecated alias for `IsPathFile`: this lands before 1.0.0 and the surface
  goes out clean.
- Breaking: two options of one field may no longer share an identity across shape
  kinds. An enum class named `str` beside a `str`, one named `date` beside a
  `date`, or one named `list[str]` beside a `list[str]` now fail at compilation
  with `Field 'x': duplicate discriminator name(s): str`. Each such pair left two
  options answering to one `$type`, with one of them unreachable — the rule
  [restrictions.md](docs/restrictions.md) already stated, now enforced where the
  implementation had only covered options sharing a runtime type. A dataclass and
  an enum of the same class name use different discriminators and remain
  admissible.

  `List` applies the same rule to its own items. It already refused two options
  of one runtime type, but not two of one identity, so a list whose elements
  answered to a single `$type` could be built directly and was caught only when a
  field was built around it. `List` is public API and its items are what its
  elements name themselves by, so the rule now runs where the two identities sit;
  the refusal names the list, `List.item: duplicate discriminator name(s): Same`.

  A refusal in one namespace no longer reads as denying an identity the other one
  publishes. A portable wrapper whose payload never reached the option it named
  arrives at validation still a dict, and in a slot with two or more dataclasses
  it was answered with the dataclass names alone — `not a choice: 'date',
  expected one of ('SA', 'SB')` — while that same `'date'` is accepted one call
  earlier when its payload parses. The refusal now carries a note saying where the
  name does belong and why the wrapper is still there.

  An option's identity is the core's to define, so the core is where it is
  checked. `pytypehintstore` had built its own guard for exactly this gap and
  refused such a schema when opening a store; that guard is now redundant, and
  the tests asserting the old division of labour describe a split that no longer
  exists. Moving the check to the layer that owns the identity is the point of
  the change, not a side effect of it.
- Breaking: `Step` requires a finite number. `nan` passed the `value <= 0` guard
  by being neither positive nor negative, and `inf` is positive without being a
  step; both reached the portable document as `NaN`/`Infinity`, which no JSON
  reader accepts, and `nan` also made a shape compare unequal to an identically
  written one, which is the property a document used as a fingerprint or a cache
  key rests on. `Step(float("nan"))` now fails with `Step.value must be finite,
  got nan`.
- Breaking: `Float` validates its `step` the way `Int` already validated its own:
  the value is a number the shape can hold, and it is finite. With `Step` itself
  refusing `nan` and `inf`, what this catches is an integer step outside the float
  range — `Float(step=Step(10**400))` fails with `Float.step: must be finite, got
  1000…` rather than compiling. A step is written into the document beside the
  bounds, and one that names no float would be read there as a bound-like number
  no float reader can use.
- Breaking: a `Float` bound written as an integer outside the float range is an
  atom error, `Float.min: must be finite, got ...`, rather than the raw
  `OverflowError` that `math.isfinite` raised converting it. `OverflowError` is
  neither `TypeError` nor `ValueError`, so it escaped every `except` the
  documented error vocabulary names. Such an integer names no float, so on a float
  shape it is not a finite one, and the question is asked in one place.
- `Struct.decode(data)` and `Signature.decode(kwargs)` take a portable tree —
  `dict`, `list`, `str`, `int`, `float`, `bool`, `None` — and return an exact
  Python one. Four things a portable tree cannot carry are restored and nothing
  else is: a `date` and a `time` spelled as text, an enum member spelled as its
  member name, and a whole `float` that arrived as `3` rather than `3.0`. See
  [decode.md](docs/decode.md).
- **`decode` is not coercion, and the distinction is load-bearing.** `"3"` never
  becomes `3`, `"true"` never becomes `True`, `""` never becomes `None`, a tuple
  never becomes a list, and a subclass never becomes its base. A `str` field
  holding `"2026-08-08"` stays a `str`. The shape decides the reading; the text
  of a value never takes part in it. Reading `"12"` as a number is interface
  policy and stays in the wrapper that knows what interface wrote it.
- `decode` never raises a schema error. Where it cannot restore a value
  unambiguously it returns it untouched, and `resolve`/`build` report it with the
  coordinates and wording they already had. One failure, reported once.
- `decode` returns a freshly built tree and never modifies the one it is given:
  every `dict` and every `list` in the result is newly built, at any depth. The
  promise is about `dict` and `list` exactly, which is all a portable tree has;
  everything else is handed along as the same object, a `dict` or `list` subclass
  included — the `OrderedDict` a `json.loads` hook produces comes back untouched,
  because rebuilding one as its base is the coercion the rule above forbids, and
  `resolve` is right to reject it. So a container reachable only through
  something a portable tree cannot carry — behind a tuple, say — is the input's
  own object, and writing into the decoded tree there writes into the input. It
  fills no defaults, runs no recipes, drops no unknown keys, and leaves absent
  keys absent — those remain `resolve`'s work. Aliasing is not preserved.
- Union routing in `decode` follows the same rule as everywhere else: the schema
  decides, and where more than one option could read a spelling, the caller names
  the option with the `$type`/`$value` grammar the core already defines. There
  are now two wrappers spelled that way, and they are documented apart. The
  **validation wrapper** covers options sharing a Python runtime type
  (`list[str] | list[int]`); `build` reads it, so `decode` keeps it and decodes
  only its payload. The **portable wrapper** covers options sharing only a
  spelling (`str | date`, `int | float`, `date | time`, two enums); `build` does
  not know it and would report `expected str | date, got dict`, so `decode`
  consumes it and hands on the exact value. Which one a slot takes is readable
  from the schema alone: options sharing a Python type are always two or more
  lists, because any other such pair is already rejected as duplicate options.
- A wrapper whose payload did not reach the option it named is left intact rather
  than consumed, so a date that failed to parse can never settle silently as the
  `str` beside it.
- `decode` is total on portable trees: it returns a value for every input and
  raises nothing but `RecursionError`, which cyclic or very deep data reaches the
  same way it does in `resolve` and `build`. An integer that no `float` equals is
  handed back rather than restored, since it is not a float written without its
  fraction, and no `OverflowError` escapes. The criterion is exactness, not
  magnitude: an integer outside the float range does not convert at all, and one
  inside it converts to a neighbour once past `2**53`, where the floats thin out
  — `float(2**53 + 1)` answers `9007199254740992.0` instead of failing.
  Restoring that neighbour would hand `build` a number the transport never
  carried, and `build` would accept it. Sixty-four-bit ids and nanosecond
  timestamps land in exactly that band.
- The spellings `decode` accepts for `date` and `time` are fixed and disjoint,
  not delegated to `fromisoformat`. That function accepts far more than a
  canonical form and its two grammars overlap: `"20200101"` reads as a date *and*
  as a time, and `"2020"` reads as `20:20`. Accepting them would let the text of a
  value select an option. `Date` takes `YYYY-MM-DD`; `Time` takes `HH:MM` or
  `HH:MM:SS`. Both are ASCII: `\d` would otherwise admit every decimal digit
  Unicode defines, leaving the spelling canonical only as far as the parser
  behind it happened to agree.
  A sub-second or offset-bearing time is still read, so `Time` reports
  its own rule rather than having the value fall through as "not a time at all".
- Enum members travel by member name, never by member value. A name is always a
  string, always identifies one member, and is what the contract publishes; a
  value may be a tuple or an object that no portable tree can carry, and the two
  readings genuinely differ — for `RED = "BLUE"; BLUE = "RED"`, `"RED"` is one
  member by name and the other by value. An alias resolves to the member it
  aliases, and the decoded member is the singleton itself, so `is` holds.
- `Struct.to_dict()` and `Signature.to_dict()` write the compiled schema as a
  portable tree: version, kind, fields or params, options, limits, notation,
  extras, defaults, enum members and nested dataclasses. It is the contract as
  data and takes no position on presentation — no widget, no input type, no
  message strings, no HTML. See [contract.md](docs/contract.md).
- The format carries `{"v": 1, ...}`. `v` rises only when a key already in it
  changes meaning or leaves; new keys do not raise it, so a reader must ignore the
  ones it does not know. It is the version of the format, never of the library.
- `to_dict()` is deterministic: equal definitions produce equal documents byte for
  byte, across processes and hash seeds, with no `sort_keys` needed. Every key is
  written in a fixed order, every sequence keeps the order the author wrote, and
  nothing derived from `id()` or from set iteration reaches the output. That is
  what makes a document usable as a fingerprint, a cache key, or one side of a
  diff.
- Structs and enums are always written as references into a definitions table,
  never inlined. Recursion terminates, a shared dataclass is described once, and a
  densely shared graph of twenty structs stays twenty-one definitions instead of
  two million nodes. Ids are class names, made unique within a document by first
  encounter (`Target`, `Target#2`), because two classes of one name can legally
  coexist in a schema and no name distinguishes them. The `name` is the contract —
  it is what travels as `$type`; the id only follows a `ref`.
  Determinism is bounded by the interpreter, not by the emitter: `python -OO`
  discards docstrings, so a signature's `doc` key disappears under that flag.
  An `id` is unique within its discriminator's namespace, which is what a sender
  needs, but not across the two — a dataclass and an enum of one class name are
  admissible together and both write that name, so options are indexed by
  position.
- `to_dict()` returns a fresh tree on every call and caches nothing, so the caller
  may modify the result at any depth without affecting the schema or a later call.
  No implementation reaches it: not the compiled `re.Pattern` behind a pattern,
  not the recipe behind a default, not a class object, not an enum member, not
  `MISSING`, and no `repr()` of anything. It never raises on a schema the core
  accepted.
- `to_dict()` asks the filesystem nothing, and nothing else outside the process
  either. Which option a value inhabits is decided by the core's own router, so it
  cannot drift from the option validation would select, and the router is asked
  the shapes themselves with nothing removed or held back. That is possible
  because no check in the core reads the world at all — see the `FileHint` entry
  above, which is where the one exception went. Determinism across processes and
  the totality of the encoding therefore hold with no exception beyond the
  `python -OO` caveat above. What remains is a slot whose value inhabits no option
  at all, reachable only through a schema assembled by hand and left
  half-compiled, and it reports `SchemaValueError` like every other schema error.
- A `Float` bound written as an integer keeps that integer whenever no `float`
  equals it, rather than publishing the nearest one. The emitter answers to the
  same exactness `decode` reads by: `Min(2**53 + 1)` written as
  `9007199254740992.0` states a bound the schema does not hold and invites a value
  the core then rejects as `too small`. A whole float still loses its fraction on
  the way out, which is the loss `decode` exists to undo.
- A bound of zero is published without its sign. `Min(0)`, `Min(0.0)` and
  `Min(-0.0)` are one atom — equal, and equal in hash — so the document they write
  has to be one document, and `-0.0` beside `0.0` made it two, which is exactly
  what a document compared byte for byte cannot afford. The normalization belongs
  to the numbers an atom carries and stops there: a default of `-0.0` keeps its
  sign, because a field holding it is not equal to one holding `0.0`, so there the
  sign is information the author wrote rather than an accident of spelling.
- A default is written in the same portable language `decode` reads, so a default
  taken from the document is valid input to the pipeline —
  `build(decode(written))` returns it — with no translation. Every certified
  default can be written this way: compilation already proved its type comes from
  the closed vocabulary, so the encoding is total and nothing is omitted, marked
  or failed on.
- The rule that names an option is about a **slot**, not about a field, and
  applies at every depth: a list element and a field of a nested dataclass name
  their option exactly as the outer field does. Writing the outer slot alone was
  the shape of one defect found while preparing this release —
  `list[str | date] = [date(...)]` was written as `["2026-08-08"]`, which `decode`
  is right to leave as text and `build` then filed under the `str` option without
  complaining. Silent, and reachable from ordinary annotations, which is the
  failure this rule is stated at the level of a slot to prevent.
- `resolve` and `build` run no foreign code while routing. A dict carrying a key
  that is not a `str` is reported as `expected string keys, got int` before the
  discriminated wrapper is looked for, because asking `"$value" in value` calls
  that key's `__eq__` on a hash collision with a reserved name — arbitrary code,
  which may raise anything, on a path that owes its caller a schema error and
  nothing else. `decode` already declined to ask the question; the validator
  declines it too.

  Every dict is typed before anything asks it a question, not only one whose slot
  has a wrapper to look for. The branch that routes between two dataclass options
  probes the same reserved key to read an inline `"$type"`, and a field of two
  dataclasses has nothing wrappable in it — so that branch used to run exactly
  the `__eq__` the guard was written to prevent, and a raising key escaped as
  whatever it felt like raising.
- The per-candidate notes on `matches no option` — one per option, recording why
  that option rejected the value — survive being carried out to their coordinates
  and the certification of a default. Reporting one level out rebuilds the error
  so the `path` can grow, and the notes are copied onto the rebuilt one, since
  dropping them there would drop exactly the detail the error was raised to
  carry. Every re-raise does this, not just the one that reports a violation one
  level out: a default that fails certification, a factory that could not be run
  at all, and a foreign `TypeError`/`ValueError` from a user's own
  `__post_init__` all keep the notes they arrived with.
- A schema error survives being rendered, whatever the size of the number in it.
  CPython refuses to render an `int` of more than `sys.get_int_max_str_digits()`
  digits — 4300 by default — so interpolating one into a message would raise
  `ValueError` on its own account, leaving "Exceeds the limit (4300 digits) for
  integer string conversion" as the reported cause and taking the real violation
  with it, `leaf` and `path` included. Above that limit the magnitude is named
  instead of shown: `too short: 1 chars, minimum <int of 16610 bits>`.

  This holds for every message the core writes, not only the numeric ones. A
  bound on a length is an ordinary integer written by the author and can be any
  size at all, so `Str` and `List` render theirs the same way — the length
  violations, the empty range, the choices certified against the bounds — and so
  do `Rows`, `MultipleOf` and the byte sizes of `FileHint`. The per-option notes
  on `matches no option` are built from the causes those checks raise, so they
  are safe once the causes are: a note explaining why an option declined can no
  longer be replaced by the digit limit that stopped it being spelled.
- The core still parses and emits no JSON text. `json.loads` and `json.dumps` are
  the caller's, and the boundary is trees, not bytes.
- Documentation: new [decode.md](docs/decode.md) and [contract.md](docs/contract.md);
  `philosophy.md` gains the distinction between decoding a representation and
  coercing a value, and states why a traversal that reports is not one of the
  interpretive helpers it refuses; `comparison.md` no longer says the core stops
  at construction; `resolve.md` states plainly that validation reaches every depth
  while filling does not; `restrictions.md` documents the discriminator-name rule
  and the union options a portable tree cannot spell bare.

## [0.0.7]

- Breaking: `IsPathFile` now guarantees that the string names a real file at the
  moment of validation, not merely that its text ends in an accepted suffix. A
  value such as `"missing.png"` previously passed on its extension alone and now
  fails with `file does not exist: 'missing.png'`. The mark validates, in this
  order: the value is exactly `str`, the ordinary `Str` limits on the text, the
  extension, `stat`, that the target is a regular file and not a directory, the
  size, and finally `Choices`. The extension is checked before the filesystem
  because it costs nothing and names the defect precisely.
- `IsPathFile` gains `min_size` and `max_size`, byte counts that are `int` or
  `None`, never negative, with `min_size` not exceeding `max_size`; `bool` is not
  accepted as an `int`. Violations report
  `IsPathFile.min_size must be int or None, got bool`,
  `IsPathFile.max_size must be >= 0, got -1` and
  `IsPathFile: min_size 100 exceeds max_size 50`. A file whose size falls outside
  the bounds fails with `file too small: 120 bytes, minimum 1024` or
  `file too large: 7000000 bytes, maximum 5242880`; an empty file is valid unless
  `min_size` is greater than zero.
- The public value remains exactly `str`. `pathlib.Path` is used only inside the
  validation, to inspect the file: nothing is coerced to `Path`, normalized,
  resolved, expanded or made absolute, so a relative path keeps its meaning
  relative to the working directory and the value stays as written.
- New failures: `file does not exist: <path>`, `not a file: <path>` for a
  directory or any non-regular target, the two size messages above, and
  `cannot inspect file <path>: <error type>: <error>` when the OS refuses the
  inspection. `FileNotFoundError` is distinguished from every other `OSError`, and
  each failure keeps its cause through `raise ... from` and its coordinate in
  `path`/`leaf` — `document: file does not exist: 'missing.pdf'`,
  `files: [1]: file too large: 7000000 bytes, maximum 5242880`.
- `Path.stat()` follows symlinks: a live link to a regular file is accepted and a
  broken one fails as non-existent. The guarantee is bounded in time — the file
  existed and met the contract when it was validated, and nothing promises it
  still does afterwards.
- Breaking: `Choices` combined with `IsPathFile` are certified against the whole
  file contract when the schema compiles, where before only their extension was
  checked. `Str.choices: file does not exist: 'default.png'` now fails
  compilation. Defaults are certified the same way, so a `signature_of` over
  `image: Annotated[str, IsPathFile()] = "default.png"` fails unless that file
  exists, is a regular file and meets the extension and size bounds.
- One internal function validates the whole contract, so `_check`, `Choices` and
  default certification cannot drift apart. `IsPathFile` remains metadata
  exclusive to `Str`: no new shape, no `PathFile` type, and no compatibility
  switch (`exists=False`, `strict=False`) — the semantics are single and explicit.

## [0.0.6]

- Breaking: `datetime.time` values with non-zero microseconds are no longer
  accepted. Time precision is limited to whole seconds, so the effective range
  is `00:00:00..23:59:59`. A value previously admissible such as
  `time(12, 30, 0, 500000)` now fails with `time precision is limited to whole
  seconds`. The rule is enforced at every entry point of the core: `Min`/`Max`
  bounds and `Choices` members at compile time, and a value wherever it is
  validated — direct check, default certification, `resolve`, `build`, and
  inside nested dataclasses, unions and lists — through the single `Time._check`.
  The failure carries its coordinate as `path`, like every other constraint.
- Following from the tighter range, `Time`'s exclusive-edge guard moves in from
  the sub-second clock edge to the whole-second one: an exclusive `Min` at
  `23:59:59` (was `time.max`) and an exclusive `Max` at `00:00:00` now report
  `exclusive bound at ... leaves no valid time`. A bound at `time.max` is instead
  rejected as sub-second precision.

## [0.0.5]

- Compilation now rejects a union of two enums that share a class name, e.g.
  two Enum classes both named `Color`, with `Field '<name>': duplicate
  discriminator name(s): Color` — the same message and recursion (into `list`
  items) that already guarded homonym dataclasses. Both options collapse to one
  `option_id()`, the public identity wrappers read to name an option, and one
  identity for two options is a defective schema. The core still routes each by
  its exact member type; the rule is about identity, not routing, so an enum and
  a dataclass of the same name never collide and stay admissible. Previously the
  core admitted the pair and only a wrapper could catch it.

## [0.0.4]

- Enum fields now accept `Extra`, the same namespaced wrapper-notation channel
  the other leaf shapes already carry. `EnumShape` gains `_extras` and a
  read-only `extras` dict; any other atom on an enum still reports `unsupported
  metadata for enum`. Dataclass (`Struct`) fields stay closed — annotate their
  fields, not the nesting.
- `Time` now rejects an exclusive bound at the clock's edge at compile time —
  `Min(time.max, exclusive=True)` and `Max(time.min, exclusive=True)` — with
  `exclusive bound at ... leaves no valid time`, symmetric with the `Date` edge.
  These bounds previously compiled while admitting no value. `Float`'s analogous
  edge is left under the "no general satisfiability" doctrine.
- `check_options_value` now attaches a PEP 678 note per candidate to a `matches
  no option` error, recording why each option rejected the value (`as <id>:
  <cause>`). The main message, `leaf` and `path` are unchanged; the notes survive
  pickle.
- Breaking (messages only): compile-time certification of an invalid default now
  reports the failure as structured data — `path` carries the field name,
  `"default"`, and any sub-path as clean coordinates, with the violation as the
  `leaf`. The rendered line reads `x: default: <leaf>`, **identical** to the
  runtime serving path (`_resolve_fields`): the same defect now reads the same
  way whether certification or serving catches it. Previously certification
  degraded the whole line into the leaf and rendered `Field 'x': default <leaf>`.
  Only the message and its structure changed; no behaviour did.

## [0.0.3]

- Unions whose options share one runtime input type now compile. `list[str] |
  list[int]` was rejected as a duplicate; both options are valid Python and
  describe different things, so the core admits them.
- Such a value selects its option through a discriminated wrapper:
  `{"$type": "list[str]", "$value": ["a", "b"]}`. `$type` is the option
  identity — `list[str]`, `list[int]`, `list[list[str]]` — and `$value` is the
  payload. The wrapper accepts no other key.
- The wrapper is required only where routing by exact runtime type is
  ambiguous. `int | str`, `list[str | int]`, `list[int] | None` and every other
  hint that already routed itself are unchanged and take no discriminator; an
  option that is alone in its runtime type does not accept one either.
- Dataclass unions keep the inline `$type` of 0.0.2 unchanged, at every depth
  and inside list items.
- Compilation still rejects options that stay indistinguishable with a
  discriminator — `list[Annotated[int, Min(0)]] | list[Annotated[int, Max(9)]]`
  share both a runtime type and an identity.
- `Shape.option_id()` returns that identity, for wrappers that need to offer the
  choice.
- No breaking change: every hint accepted by 0.0.2 compiles and behaves as
  before.

## [0.0.2]

- `Extra(value)` becomes `Extra(key, value)`, with a namespaced key
  (`"package.name"`) and any string value, empty included.
- Shapes replace `extra` with `extras`, a read-only `dict[str, str]` merged from
  every `Extra` atom on the hint. Keys layer independently: the outer atom wins.

## [0.0.1] - 2026-07-15

- Initial release.
