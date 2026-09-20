class _MissingType:
    def __repr__(self):
        return "MISSING"

    # Copy and pickle must preserve the singleton.
    def __reduce__(self):
        return "MISSING"


MISSING = _MissingType()


def type_name(obj) -> str:
    return type(obj).__name__


# Reporting huge integers must survive CPython's decimal digit limit.
def render_number(value) -> str:
    try:
        return str(value)
    except ValueError:
        if type(value) is tuple:
            inner = ", ".join(render_number(v) for v in value)
            return f"({inner},)" if len(value) == 1 else f"({inner})"
        return f"<int of {value.bit_length()} bits>"


def check_opt(owner: str, attr: str, value, expected: type) -> None:
    if value is not None and type(value) is not expected:
        raise TypeError(f"{owner}.{attr} must be {expected.__name__}, got {type(value).__name__}")
