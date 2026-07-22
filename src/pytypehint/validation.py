from pytypehint.errors import SchemaTypeError, SchemaValueError


def accepted(shapes) -> str:
    # Options that share a runtime type name it once: the report is about the
    # type the value should have had, not about which option it would have hit.
    return " | ".join(dict.fromkeys(shape.pytype.__name__ for shape in shapes))


def _accepts(shape, value) -> bool:
    try:
        shape._check(value)
    except (TypeError, ValueError):
        return False
    return True


# A Python value is a real object, not input data: it carries no discriminator,
# and none can be attached to it. Options sharing its runtime type are therefore
# separated by what they accept. This is not a guess between them — a value that
# satisfies several rematerializes identically through any of them, because
# rematerialization routes each element by its own exact type.
def value_branch(shapes, value):
    candidates = [shape for shape in shapes if type(value) is shape.pytype]
    if len(candidates) < 2:
        return candidates[0] if candidates else None
    return next((shape for shape in candidates if _accepts(shape, value)), None)


def check_options_value(shapes, value) -> None:
    candidates = [shape for shape in shapes if type(value) is shape.pytype]
    if len(candidates) == 1:
        # One candidate reports its own violation, with its own coordinates.
        candidates[0]._check(value)
        return

    if candidates:
        if any(_accepts(shape, value) for shape in candidates):
            return
        options = " | ".join(shape.option_id() for shape in candidates)
        # The leaf names which options were tried; a note per candidate records
        # why each rejected the value, so the failure is diagnosable without
        # re-running the checks by hand. The main message is unchanged.
        error = SchemaValueError(f"matches no option: {options}")
        for shape in candidates:
            try:
                shape._check(value)
            except (TypeError, ValueError) as cause:
                error.add_note(f"as {shape.option_id()}: {cause}")
        raise error

    raise SchemaTypeError(f"expected {accepted(shapes)}, got {type(value).__name__}")
