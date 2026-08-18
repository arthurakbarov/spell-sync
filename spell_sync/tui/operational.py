"""Expected operational failures for TUI fail-open paths."""

from textual.css.query import QueryError

# Keep UI responsive without swallowing programming defects like AssertionError.
OPERATIONAL_EXCEPTIONS = (
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    LookupError,
    QueryError,
)
