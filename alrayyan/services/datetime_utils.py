from datetime import datetime, timezone


def as_utc_naive(value):
    """Normalize naive or aware datetimes to naive UTC for legacy DB comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        # Existing DateTime columns store UTC values without timezone metadata.
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
