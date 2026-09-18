"""Pure grid focus model. ZERO Flet imports, ZERO side effects."""

from enum import Enum


class Direction(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


def focus_move(index: int, direction: Direction, *, count: int, columns: int) -> int:
    """Pure grid focus movement. CLAMP at edges (no wrap). Returns new index."""
    if count <= 0:
        return 0
    # Clamp index into valid range first
    index = max(0, min(index, count - 1))

    row, col = divmod(index, columns)

    if direction is Direction.LEFT:
        if col == 0:
            return index
        return index - 1

    if direction is Direction.RIGHT:
        new = index + 1
        if col >= columns - 1 or new >= count:
            return index
        return new

    if direction is Direction.UP:
        if row == 0:
            return index
        return index - columns

    # DOWN
    new = index + columns
    if new >= count:
        # Clamp to last valid index in the same column below, if any
        last_row = (count - 1) // columns
        if row >= last_row:
            return index
        # Target the same column in the last valid row
        clamped = last_row * columns + col
        return min(clamped, count - 1)
    return new
