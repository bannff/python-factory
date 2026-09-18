"""Tests for wall.focus -- pure grid focus movement. AAA, behavior-named."""

from wall.focus import Direction, focus_move

D = Direction


# --- Interior moves ---

def test_right_moves_one_column():
    assert focus_move(0, D.RIGHT, count=8, columns=4) == 1


def test_left_moves_one_column():
    assert focus_move(1, D.LEFT, count=8, columns=4) == 0


def test_down_moves_one_row():
    assert focus_move(1, D.DOWN, count=8, columns=4) == 5


def test_up_moves_one_row():
    assert focus_move(5, D.UP, count=8, columns=4) == 1


# --- Edge clamping (no wrap) ---

def test_left_on_column_zero_is_noop():
    assert focus_move(0, D.LEFT, count=8, columns=4) == 0
    assert focus_move(4, D.LEFT, count=8, columns=4) == 4


def test_right_on_last_column_is_noop():
    assert focus_move(3, D.RIGHT, count=8, columns=4) == 3
    assert focus_move(7, D.RIGHT, count=8, columns=4) == 7


def test_right_on_last_item_is_noop():
    # 6 items, 4 cols: last item at index 5 (col 1 of row 1)
    assert focus_move(5, D.RIGHT, count=6, columns=4) == 5


def test_up_on_row_zero_is_noop():
    assert focus_move(2, D.UP, count=8, columns=4) == 2


def test_down_past_last_row_is_noop():
    # 4 items, 4 columns -> only row 0
    assert focus_move(2, D.DOWN, count=4, columns=4) == 2


# --- Partial last row DOWN clamp ---

def test_down_into_partial_last_row_clamps_to_valid():
    # 6 items, 4 cols: row0=[0,1,2,3], row1=[4,5]
    # From index 2 (row0, col2), down -> row1 col2 doesn't exist -> clamp to 5
    assert focus_move(2, D.DOWN, count=6, columns=4) == 5


def test_down_into_partial_row_exact_column_exists():
    # 6 items, 4 cols: from index 1 (row0, col1) -> row1 col1 = index 5
    assert focus_move(1, D.DOWN, count=6, columns=4) == 5


# --- Degenerate cases ---

def test_single_item_grid_all_directions_noop():
    for d in Direction:
        assert focus_move(0, d, count=1, columns=4) == 0


def test_count_zero_returns_zero():
    assert focus_move(5, D.RIGHT, count=0, columns=4) == 0


def test_out_of_range_index_clamps_first():
    # index 99 with count=8 -> clamp to 7, then move left -> 6
    assert focus_move(99, D.LEFT, count=8, columns=4) == 6


def test_negative_index_clamps_to_zero():
    assert focus_move(-3, D.RIGHT, count=8, columns=4) == 1


# --- columns=1 edge cases ---

def test_columns_one_left_always_noop():
    assert focus_move(2, D.LEFT, count=5, columns=1) == 2


def test_columns_one_right_always_noop():
    assert focus_move(2, D.RIGHT, count=5, columns=1) == 2


def test_columns_one_down_moves():
    assert focus_move(2, D.DOWN, count=5, columns=1) == 3


def test_columns_one_up_moves():
    assert focus_move(2, D.UP, count=5, columns=1) == 1
