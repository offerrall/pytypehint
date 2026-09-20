# Defaults

Defaults are certified when `struct_of` or `signature_of` compiles the schema,
then rematerialized and validated whenever their key is missing.
A supplied key never runs its default recipe.

| Default | Each missing-key serving |
|---|---|
| Scalar, `date`, `time`, `None` | Reused; immutable |
| Enum member | Reused; singleton |
| List | New list, contents rematerialized recursively |
| Tuple | Contents rematerialized recursively |
| Dataclass instance | Reconstructed through its constructor |
| `default_factory` | Called again |

Factories run once for certification and once per serving. Instance reconstruction
runs `__init__` and `__post_init__`; equality is preserved, internal aliases are
not. Tuple immutability does not cause mutable contents to be shared.

Recipes must be pure and deterministic, without shared mutable state or observable
side effects. Do not mutate recipe objects or the certified `Field.default`.
The core cannot enforce purity, but invalid values fail both at certification and
at serving, with a `default` path segment:

```text
count: default: expected int, got str
```

Use `field(default_factory=...)` for mutable dataclass field defaults, as Python
requires. Function defaults have no such restriction, but fresh defaults apply
only through `signature_of(fn).resolve(...)` or `.build(...)`. Calling the function
directly retains Python's usual shared-default behavior.
