# Defaults

A default is a recipe. It is certified when the schema compiles and
rematerialized whenever a build or resolve omits its key.

| Default | Rematerialization |
|---|---|
| `int`, `float`, `str`, `bool`, `date`, `time`, `None` | passed as is; immutable |
| Enum member | passed as is; members are singletons |
| list | fresh list; items rematerialized recursively |
| dataclass instance | reconstructed through its constructor |
| `default_factory` | factory called again |

Recipes run once at `struct_of`/`signature_of` for certification and once per
missing-key serving. A provided key never runs its recipe. The served value is
validated each time, so an impure recipe that drifts outside its schema
fails with a `default` path segment.

Defaults must be pure and deterministic: same recipe, equal result, no shared
mutable state or observable side effects. The core cannot prove that promise.
Mutating an externally held recipe object or the certified `field.default`
violates the same rule from outside and remains the author's responsibility. The
same promise covers the input: `build` validates it once and constructs from it,
so the core watches neither concurrent mutation nor a `__post_init__` that edits
the input data. See [build.md](build.md).

Instance reconstruction preserves equality, not internal alias topology. It
runs `__init__` and `__post_init__` on every serving.

Python rejects a non-frozen dataclass instance used directly as a dataclass
field default before pytypehint runs (`ValueError: mutable default ... is not
allowed`). Use `field(default_factory=...)`. Function defaults have no such
Python restriction and may use an instance directly.

Calling a function directly still uses Python's shared defaults. Fresh function
defaults apply only when data passes through `signature_of(fn).resolve(...)` or
`.build(...)`.
