class _MissingType:
    def __repr__(self):
        return "MISSING"

    # Sentinel: pickle/copy must round-trip to the one instance, not a clone.
    # Returning the global's name makes both resolve back to this singleton.
    def __reduce__(self):
        return "MISSING"


MISSING = _MissingType()


def type_name(obj) -> str:
    return type(obj).__name__


# CPython refuses to render an int with more than `sys.get_int_max_str_digits()`
# decimal digits — 4300 by default — so interpolating one into a message raises
# ValueError of its own. An error has to survive being reported: the failure is
# the value being out of range, and a report that fails instead loses both the
# leaf and the path. Above that limit the magnitude is named rather than shown.
def render_number(value) -> str:
    try:
        return str(value)
    except ValueError:
        # Only reached where `str` already refused, so the spelling of everything
        # that renders normally is untouched. A tuple of choices is rebuilt the
        # way `str` would have spelled it, trailing comma and all.
        if type(value) is tuple:
            inner = ", ".join(render_number(v) for v in value)
            return f"({inner},)" if len(value) == 1 else f"({inner})"
        return f"<int of {value.bit_length()} bits>"


def check_opt(owner: str, attr: str, value, expected: type) -> None:
    if value is not None and type(value) is not expected:
        raise TypeError(f"{owner}.{attr} must be {expected.__name__}, got {type(value).__name__}")
