# Restrictions

Only the [documented types](vocabulary.md) and [atoms](atoms.md) are supported.
Unsupported hints and invalid schemas fail during compilation.

| Definition | Restriction |
|---|---|
| Lists | Must specify an item type |
| Tuples | Fixed positions, `tuple[X, ...]` or `tuple[()]`; no bare or unpacked hints |
| `None` | Must accompany another option, including in sequence slots |
| `Literal` | Uniform `int` or `str` values only |
| Enum | Must have members; `Flag` and `IntFlag` are unsupported |
| Dataclass | Every field needs a hint; no `InitVar` or `init=False` fields |
| Function | Plain named function only; no lambdas, bound methods, partials or callable objects |
| Parameters | Hinted and callable by keyword; no positional-only, `*args` or `**kwargs` |
| `self` / `cls` | An unhinted leading receiver is rejected as an unbound method |
| Nested items | No field atoms on list items or tuple positions |
| Extra metadata | Keys must be namespaced; values must be strings |

Wrap a bound operation in a plain function:

```python
def search(query: str):
    return service.search(query)
```

`datetime`, path objects, mappings, sets and arbitrary classes are outside the
vocabulary. Use dataclasses to represent additional structure or policy.

## Option identity

`Shape.option_id()` gives the name used by [union discriminators](build.md#union-selection).
Constraints do not change that identity.

| Shape | Identity |
|---|---|
| Scalar | `int`, `float`, `str`, `bool`, `date`, `time` |
| `NoneShape` | `None` |
| Enum or dataclass | Class name |
| List | `list[str]`, `list[int \| None]`, etc. |
| Tuple | `tuple[int, str]`, `tuple[int, ...]`, `tuple[()]`, etc. |

Identities must be unique among dataclass options and separately among all other
options in each slot. A dataclass and enum may share a name; two dataclasses or
two enums may not. An enum named `str` cannot sit beside the `str` option.

Options sharing both runtime type and identity are rejected, even with different
constraints: `Literal["a"] | str`, two constrained `int` variants, or two lists
whose item constraints differ but whose identities are both `list[int]`.
Merge them into one option or use named dataclasses. Different list/tuple
identities are valid. Variants sharing the same runtime type require a wrapper;
contents never choose the variant.

## Runtime limits

- Validation requires exact types, including plain dictionaries and exact lists
  or tuples. Input dataclass instances are rejected; defaults may be instances.
- Floats, bounds, choices and numeric steps must be finite. Integer float bounds
  that overflow float conversion are rejected; finite nonrepresentable integers
  remain exact bounds.
- Times must be naive and have zero microseconds. Exclusive temporal bounds
  excluding the whole date/time domain fail at compilation.
- Known atom contradictions and invalid defaults fail at compilation. There is
  no general satisfiability proof across independent constraints.
- Validation stops at the first error. Constructor exceptions propagate unchanged.
- Cycles and excessive nesting may raise raw `RecursionError` in decode, resolve
  or build. Recursive schemas are supported; cyclic input values are not.
- Factories must be pure, and input must not change during construction.

`FileHint` checks the string's suffix only; existence, kind and size require
consumer checks. Portable spelling collisions need [decode wrappers](decode.md#unions),
even when their restored Python types would be distinct.
