from __future__ import annotations

import pytest

from bot.services.games.connect_four import COLS, ROWS, Connect4
from bot.services.games.tic_tac_toe import TicTacToe


class FakeMember:
    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FakeMember) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class FakeGamesCog:
    def register_game(self, thread_id: int, game: object) -> None:
        pass

    def unregister_game(self, thread_id: int) -> None:
        pass


def ttt_game() -> tuple[TicTacToe, FakeMember, FakeMember]:
    a, b = FakeMember(1, "A"), FakeMember(2, "B")
    return TicTacToe(FakeGamesCog(), [a, b]), a, b


def c4_game() -> tuple[Connect4, FakeMember, FakeMember]:
    a, b = FakeMember(1, "A"), FakeMember(2, "B")
    return Connect4(FakeGamesCog(), [a, b]), a, b


def test_ttt_turns_alternate_and_wrap() -> None:
    g, a, b = ttt_game()
    assert g.current_player in (a, b)
    starter = g.current_player
    other = b if starter is a else a
    g.next_turn()
    assert g.current_player is other
    g.next_turn()
    assert g.current_player is starter


TTT_WIN_LINES = [
    [(0, 0), (0, 1), (0, 2)],
    [(1, 0), (1, 1), (1, 2)],
    [(2, 0), (2, 1), (2, 2)],
    [(0, 0), (1, 0), (2, 0)],
    [(0, 1), (1, 1), (2, 1)],
    [(0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 2), (1, 1), (2, 0)],
]


@pytest.mark.parametrize("line", TTT_WIN_LINES)
def test_ttt_winning_lines(line: list[tuple[int, int]]) -> None:
    g, _, _ = ttt_game()
    for r, c in line:
        g.board[r][c] = "❌"
    assert g.get_winner() is not None
    assert g.is_game_over()


TTT_DRAW_BOARDS = [
    [
        ["❌", "⭕", "❌"],
        ["❌", "⭕", "⭕"],
        ["⭕", "❌", "❌"],
    ],
    [
        ["❌", "⭕", "⭕"],
        ["⭕", "❌", "❌"],
        ["❌", "⭕", "⭕"],
    ],
]


@pytest.mark.parametrize("board", TTT_DRAW_BOARDS)
def test_ttt_draw_boards(board: list[list[str]]) -> None:
    g, _, _ = ttt_game()
    g.board = [row[:] for row in board]
    assert g.get_winner() is None
    assert g.is_game_over()


def test_ttt_open_board_not_over() -> None:
    g, _, _ = ttt_game()
    assert not g.is_game_over()


def test_c4_gravity_stacks() -> None:
    c, _, _ = c4_game()
    assert c._drop_row(0) == ROWS - 1
    c.board[ROWS - 1][0] = "🔴"
    assert c._drop_row(0) == ROWS - 2


C4_WIN_PLACEMENTS = [
    [(5, 0), (4, 0), (3, 0), (2, 0)],
    [(5, 0), (5, 1), (5, 2), (5, 3)],
    [(2, 0), (3, 1), (4, 2), (5, 3)],
    [(2, 3), (3, 2), (4, 1), (5, 0)],
]


@pytest.mark.parametrize("cells", C4_WIN_PLACEMENTS)
def test_c4_winning_placements(cells: list[tuple[int, int]]) -> None:
    c, _, _ = c4_game()
    for r, col in cells:
        c.board[r][col] = "🔴"
    assert c.get_winner() is not None


def test_c4_vertical_via_drops() -> None:
    c, _, _ = c4_game()
    for col in (0, 1, 0, 1, 0, 1, 0):
        row = c._drop_row(col)
        c.board[row][col] = "🔴"
    assert c.get_winner() is not None


def test_c4_dense_board_is_draw() -> None:
    c, _, _ = c4_game()
    for r in range(ROWS):
        for col in range(COLS):
            c.board[r][col] = "🔴" if "RRYY"[(col + 2 * r) % 4] == "R" else "🟡"
    assert c.get_winner() is None
    assert c.is_game_over()


def test_c4_full_top_row_is_over() -> None:
    c, _, _ = c4_game()
    for col in range(COLS):
        c.board[0][col] = "🔴"
    assert all(c.is_column_full(col) for col in range(COLS))
    assert c.is_game_over()
