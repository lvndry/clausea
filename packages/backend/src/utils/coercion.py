"""Lenient value coercion for LLM output."""

from typing import Annotated

from pydantic import BeforeValidator


def coerce_bool(value: object) -> bool:
    """Lenient bool for LLM output. Cheaper/free models emit strings like
    "yes"/"required"/"unclear" where the schema expects a bool; pydantic's default
    bool coercion rejects those, which would drop the whole payload. Map the common
    representations; unknown/None -> False (the conservative default).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "yes", "y", "required", "1"}:
            return True
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value != 0
    return False


LenientBool = Annotated[bool, BeforeValidator(coerce_bool)]
"""A bool field that accepts the loose string/number forms free models emit."""
