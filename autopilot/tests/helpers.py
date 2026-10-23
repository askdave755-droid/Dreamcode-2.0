"""Shared test helpers. Never import conftest directly — it has import side effects."""
_counter = {"n": 0}


def unique_number() -> str:
    """A distinct, valid NANP number for each call."""
    _counter["n"] += 1
    return f"+141855{_counter['n']:05d}"
