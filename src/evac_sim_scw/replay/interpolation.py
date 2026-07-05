from __future__ import annotations


def interpolate_agent(a: list, b: list, alpha: float) -> list:
    result = a.copy()
    for index in (1, 2, 3, 6, 7):
        result[index] = a[index] + (b[index] - a[index]) * alpha
    result[4] = b[4] if alpha >= 0.5 else a[4]
    result[5] = b[5] if alpha >= 0.5 else a[5]
    return result
