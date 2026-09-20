def _render(path, leaf: str) -> str:
    return "".join(f"[{s}]: " if type(s) is int else f"{s}: " for s in path) + leaf


# Pickle the original leaf and path, not the rendered exception args.
def _reduce(error):
    return (type(error), (error.leaf, error.path), error.__dict__)


class SchemaTypeError(TypeError):

    def __init__(self, leaf: str, path: tuple = ()):
        self.leaf = leaf
        self.path: tuple = tuple(path)
        super().__init__(_render(self.path, self.leaf))

    def __reduce__(self):
        return _reduce(self)


class SchemaValueError(ValueError):

    def __init__(self, leaf: str, path: tuple = ()):
        self.leaf = leaf
        self.path: tuple = tuple(path)
        super().__init__(_render(self.path, self.leaf))

    def __reduce__(self):
        return _reduce(self)


def _renote(rebuilt: Exception, original: Exception) -> Exception:
    for note in getattr(original, "__notes__", ()):
        rebuilt.add_note(note)
    return rebuilt


def _prefixed(error: Exception, path: tuple) -> Exception:
    if isinstance(error, (SchemaTypeError, SchemaValueError)):
        return _renote(type(error)(error.leaf, (*path, *error.path)), error)
    cls = SchemaTypeError if isinstance(error, TypeError) else SchemaValueError
    return _renote(cls(str(error), path), error)
