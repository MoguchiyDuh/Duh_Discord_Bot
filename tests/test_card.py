from __future__ import annotations

import pytest

import discord

from bot.music.card import (
    PlayerCardView,
    format_seconds,
    render_card,
    render_tombstone,
)
from conftest import make_track


def test_render_now_shows_progress_requester_and_volume(make_player) -> None:
    p = make_player()
    track = make_track("A")
    track.requester = "Kirill"
    p.current = track

    embed = render_card(p)
    assert embed.title.startswith("🎶 A")
    assert "💠" in embed.description
    assert "Kirill" in embed.description
    assert "Volume 100%" in embed.footer.text


def test_render_queue_page(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    p.queue.append(make_track("B"))
    p.page = "queue"

    embed = render_card(p)
    assert "Queue" in embed.title


def test_render_queue_page_respects_field_limit(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    long_title = "L" * 60
    for i in range(50):
        t = make_track(f"{long_title}{i}")
        t.requester = "VeryLongRequesterName"
        p.queue.append(t)
    p.page = "queue"

    embed = render_card(p)
    for field in embed.fields:
        assert len(field.value) <= 1024
    assert "next page" in embed.fields[0].value


def test_render_history_page(make_player) -> None:
    p = make_player()
    p.current = make_track("B")
    p.history.append(make_track("A"))
    p.page = "history"

    embed = render_card(p)
    assert "History" in embed.title


def test_render_idle(make_player) -> None:
    p = make_player()
    p.current = None
    p.queue.clear()

    embed = render_card(p)
    assert embed.title.startswith("💤")


def test_card_view_has_17_unique_button_ids(make_player) -> None:
    p = make_player()
    view = PlayerCardView(p.cog, p)
    ids = [child.custom_id for child in view.children]
    assert len(ids) == 17
    assert len(set(ids)) == 17


def test_card_view_sync_now_page_shows_transport(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    p.mix_url = "https://mymix"
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert view.prev in view.children and view.skip in view.children
    assert view.page_back not in view.children
    assert not view.seek_back.disabled
    assert view.mix_toggle.style == discord.ButtonStyle.success


def test_card_view_sync_idle_now_page_hides_transport(make_player) -> None:
    p = make_player()
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert view.prev not in view.children
    assert view.mix_toggle.disabled
    assert view.nav_queue.disabled


def test_card_view_sync_queue_page_shows_paging(make_player) -> None:
    p = make_player()
    p.page = "queue"
    for i in range(25):
        p.queue.append(make_track(f"t{i}"))
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert view.page_back in view.children and view.page_fwd in view.children
    assert view.prev not in view.children
    assert view.page_back.disabled
    assert not view.page_fwd.disabled
    assert view.nav_queue.style == discord.ButtonStyle.success


def test_card_view_play_pause_reflects_state(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    p.voice.source = object()
    p.voice.playing = True
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert "⏸" in str(view.play_pause.emoji)
    assert view.play_pause.style == discord.ButtonStyle.primary

    p.voice.pause()
    view.sync()
    assert "▶" in str(view.play_pause.emoji)
    assert view.play_pause.style == discord.ButtonStyle.success


def test_card_view_sync_history_page_paging(make_player) -> None:
    p = make_player()
    p.page = "history"
    for i in range(12):
        p.history.append(make_track(f"h{i}"))
    p.history_page = 1
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert not view.page_back.disabled
    assert view.page_fwd.disabled
    assert view.nav_history.style == discord.ButtonStyle.success


def test_render_history_pagination(make_player) -> None:
    p = make_player()
    for i in range(25):
        p.history.append(make_track(f"h{i}"))
    p.page = "history"
    p.history_page = 1

    embed = render_card(p)
    assert "Page 2/3" in embed.footer.text
    assert "11." in embed.description


def test_render_tombstone(make_player) -> None:
    p = make_player()
    p.tracks_played = 2
    p.listen_seconds = 65
    embed = render_tombstone(p)
    assert "Session ended" in embed.title
    assert "2 tracks" in embed.description


async def test_position_picker_routes_front_flag() -> None:
    from bot.music.card import PositionPickerView

    calls: list[bool] = []

    class PickerCog:
        player = None

        async def act_add(self, interaction, player, query, *, front):
            calls.append(front)

    class FakeResponse:
        async def edit_message(self, **kwargs):
            pass

    class FakeInteraction:
        response = FakeResponse()

    cog = PickerCog()
    player = object()
    view = PositionPickerView(cog, player, "night of nights", "Kirill")
    assert len(view.children) == 2
    await view._choose(FakeInteraction(), False)
    await view._choose(FakeInteraction(), True)
    assert calls == [False, True]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (3661, "1:01:01"),
        (59, "0:59"),
        (60, "1:00"),
        (0, "0:00"),
        (None, "0:00"),
        (-5, "0:00"),
    ],
)
def test_format_seconds(seconds: float | int | None, expected: str) -> None:
    assert format_seconds(seconds) == expected
