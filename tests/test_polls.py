from __future__ import annotations

import time

import discord

from bot.cogs.polls import Poll, PollView
from conftest import FakeMessage


def make_poll(**kwargs) -> Poll:
    defaults = {
        "question": "Best lang?",
        "choices": ["Rust", "Python", "C"],
        "minutes": 5,
        "multi": False,
        "requester": "Kirill",
    }
    defaults.update(kwargs)
    return Poll(**defaults)


def test_vote_single_add_move_remove() -> None:
    poll = make_poll()
    poll.vote(1, 0)
    assert poll.tally() == [1, 0, 0]
    poll.vote(1, 2)
    assert poll.tally() == [0, 0, 1]
    assert len(poll.votes) == 1
    poll.vote(1, 2)
    assert poll.tally() == [0, 0, 0]
    assert 1 not in poll.votes


def test_vote_multi_toggles() -> None:
    poll = make_poll(multi=True)
    poll.vote(1, 0)
    poll.vote(1, 1)
    assert poll.tally() == [1, 1, 0]
    poll.vote(1, 0)
    assert poll.tally() == [0, 1, 0]


def test_two_voters() -> None:
    poll = make_poll()
    poll.vote(1, 0)
    poll.vote(2, 0)
    poll.vote(3, 1)
    assert poll.tally() == [2, 1, 0]


def test_render_live_and_final() -> None:
    poll = make_poll()
    poll.vote(1, 0)
    poll.vote(2, 0)
    poll.vote(3, 1)

    live = poll.render()
    assert "Best lang?" in live.title
    assert "Ends in" in live.footer.text
    assert "Kirill" in live.footer.text
    assert "2 (67%)" in live.description
    assert "▰" in live.description

    poll.finalized = False
    final = poll.render(final=True)
    assert "🏁" in final.title
    assert "🏆 Rust" in final.description
    assert "Final results" in final.footer.text


def test_render_tie_lists_all_winners() -> None:
    poll = make_poll()
    poll.vote(1, 0)
    poll.vote(2, 1)
    final = poll.render(final=True)
    assert "🏆 Rust • Python" in final.description
    assert final.description.count("🏆") == 1


def test_render_no_votes_final() -> None:
    poll = make_poll()
    final = poll.render(final=True)
    assert "No votes" in final.description


def test_view_buttons_and_callback(make_player_none=None) -> None:
    poll = make_poll()
    view = PollView(poll)
    assert len(view.children) == 3
    assert all(isinstance(c, discord.ui.Button) for c in view.children)
    assert all(not c.disabled for c in view.children)


async def test_vote_callback_refreshes_message() -> None:
    poll = make_poll()
    view = PollView(poll)
    poll.message = FakeMessage(1)

    class FakeUser:
        id = 42

    class FakeResponse:
        async def defer(self):
            pass

    class FakeInteraction:
        user = FakeUser()
        response = FakeResponse()

    button = view.children[1]
    await button.callback(FakeInteraction())
    assert poll.tally() == [0, 1, 0]
    assert len(poll.message.edits) == 1


async def test_finalize_disables_and_edits() -> None:
    poll = make_poll()
    view = PollView(poll)
    poll.message = FakeMessage(1)
    poll.vote(1, 2)

    await poll.finalize()
    assert poll.finalized
    assert all(c.disabled for c in view.children)
    assert len(poll.message.edits) == 1
    assert poll.message.edits[0]["embed"].title.startswith("🏁")
    assert poll.message.edits[0]["view"] is view

    edits_before = len(poll.message.edits)
    await poll.finalize()
    assert len(poll.message.edits) == edits_before


async def test_run_with_past_deadline_finalizes() -> None:
    poll = make_poll()
    view = PollView(poll)
    poll.message = FakeMessage(1)
    poll.ends_at = time.monotonic() - 1

    await poll.run()
    assert poll.finalized
    assert all(c.disabled for c in view.children)


async def test_refresh_on_deleted_message_stops_poll() -> None:
    from unittest.mock import patch

    poll = make_poll()
    PollView(poll)
    poll.message = FakeMessage(1)

    fake_response = type("R", (), {"status": 404, "reason": "Not Found"})()

    async def raise_not_found(self, **kwargs):
        raise discord.NotFound(fake_response, {"message": "Unknown Message"})

    with patch.object(FakeMessage, "edit", raise_not_found):
        await poll.refresh()
    assert poll.finalized
