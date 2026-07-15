"""Structured validation errors.

Every validation failure carries the coordinate where it happened as data, not
only inside its message. `path` walks from the root of the supplied input to the
value that failed; `leaf` is the failure itself, with no path attached. `str()`
renders the two into the exact line the schema has always produced, so wrappers
can keep matching on text or switch to the structure.
"""


def _render(path, leaf: str) -> str:
    # Integers are list indexes and render as "[0]"; everything else is a key.
    return "".join(f"[{s}]: " if type(s) is int else f"{s}: " for s in path) + leaf


# BaseException.__reduce__ would rebuild from `args`, which holds the rendered
# line — reconstruction would land on leaf=<whole line>, path=(), and only the
# trailing state dict would put it right. Rebuild from the real arguments
# instead, and keep the state so add_note() and wrapper attributes survive too.
def _reduce(error):
    return (type(error), (error.leaf, error.path), error.__dict__)


class SchemaTypeError(TypeError):
    """A value had the wrong type. Subclasses TypeError; existing handlers still catch it."""

    def __init__(self, leaf: str, path: tuple = ()):
        self.leaf = leaf
        self.path: tuple = tuple(path)
        # A single arg keeps str(error) equal to the rendered line.
        super().__init__(_render(self.path, self.leaf))

    def __reduce__(self):
        return _reduce(self)


class SchemaValueError(ValueError):
    """A value had the right type but broke a constraint. Subclasses ValueError."""

    def __init__(self, leaf: str, path: tuple = ()):
        self.leaf = leaf
        self.path: tuple = tuple(path)
        super().__init__(_render(self.path, self.leaf))

    def __reduce__(self):
        return _reduce(self)


def _prefixed(error: Exception, path: tuple) -> Exception:
    """Re-raise `error` one level out, with `path` prepended and its leaf intact."""
    if isinstance(error, (SchemaTypeError, SchemaValueError)):
        return type(error)(error.leaf, (*path, *error.path))
    # A foreign TypeError/ValueError — a user factory or __post_init__ — has no
    # structure to preserve, so its whole message becomes the leaf.
    cls = SchemaTypeError if isinstance(error, TypeError) else SchemaValueError
    return cls(str(error), path)
