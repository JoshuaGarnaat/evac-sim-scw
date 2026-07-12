from __future__ import annotations


def interpolate_agent(a: list, b: list, alpha: float) -> list:
    """Linearly interpolate an agent record between two replay frames."""
    result = a.copy()
    # Packed replay fields 1-3 and 6-7 are continuous; floor and state are categorical.
    for index in (1, 2, 3, 6, 7):
        result[index] = a[index] + (b[index] - a[index]) * alpha
    result[4] = b[4] if alpha >= 0.5 else a[4]
    result[5] = b[5] if alpha >= 0.5 else a[5]
    return result
