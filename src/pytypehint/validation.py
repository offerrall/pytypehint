from pytypehint.errors import SchemaTypeError, SchemaValueError


def accepted(shapes) -> str:
    return " | ".join(dict.fromkeys(shape.pytype.__name__ for shape in shapes))


def _accepts(shape, value) -> bool:
    try:
        shape._check(value)
    except (TypeError, ValueError):
        return False
    return True


# Authored defaults have no discriminator; input data uses explicit routing.
def value_branch(shapes, value):
    candidates = [shape for shape in shapes if type(value) is shape.pytype]
    if len(candidates) < 2:
        return candidates[0] if candidates else None
    return next((shape for shape in candidates if _accepts(shape, value)), None)


def check_options_value(shapes, value) -> None:
    candidates = [shape for shape in shapes if type(value) is shape.pytype]
    if len(candidates) == 1:
        candidates[0]._check(value)
        return

    if candidates:
        if any(_accepts(shape, value) for shape in candidates):
            return
        options = " | ".join(shape.option_id() for shape in candidates)
        error = SchemaValueError(f"matches no option: {options}")
        for shape in candidates:
            try:
                shape._check(value)
            except (TypeError, ValueError) as cause:
                error.add_note(f"as {shape.option_id()}: {cause}")
        raise error

    raise SchemaTypeError(f"expected {accepted(shapes)}, got {type(value).__name__}")
