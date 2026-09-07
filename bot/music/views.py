from __future__ import annotations

import contextlib

import discord

from bot.services.youtube import Track


def parse_selection(selection: str, max_count: int) -> set[int]:
    indices: set[int] = set()
    try:
        for part in selection.replace(" ", "").split(","):
            if "-" in part:
                start_raw, _, end_raw = part.partition("-")
                start, end = int(start_raw), int(end_raw)
                if start < 1 or end > max_count or start > end:
                    continue
                indices.update(range(start, end + 1))
            else:
                index = int(part)
                if 1 <= index <= max_count:
                    indices.add(index)
    except ValueError:
        return set()
    return indices


class _SelectionView(discord.ui.View):
    def __init__(self, user_id: int, timeout: float) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "You didn't initiate this request!", ephemeral=True
        )
        return False

    async def dispose(self, content: str) -> None:
        self.stop()
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(content=content, view=None, embed=None)

    async def on_timeout(self) -> None:
        await self.dispose("⏱️ Timed out.")


class TrackSelectionView(_SelectionView):
    def __init__(
        self, tracks: list[Track], user_id: int, timeout: float = 60.0
    ) -> None:
        super().__init__(user_id, timeout)
        self.tracks = tracks
        self.selected: Track | None = None
        for index in range(len(tracks)):
            self.add_item(_TrackButton(index))
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger)
        cancel.callback = self._cancel
        self.add_item(cancel)

    async def _cancel(self, interaction: discord.Interaction) -> None:
        await self.dispose("Cancelled.")


class _TrackButton(discord.ui.Button[TrackSelectionView]):
    def __init__(self, index: int) -> None:
        super().__init__(
            label=str(index + 1),
            style=discord.ButtonStyle.primary,
            row=index // 3,
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if view is None:
            return
        view.selected = view.tracks[self.index]
        await view.dispose(f"➕ **{view.selected.title}**")


class PlaylistSelectionView(_SelectionView):
    def __init__(self, track_count: int, user_id: int, timeout: float = 60.0) -> None:
        super().__init__(user_id, timeout)
        self.track_count = track_count
        self.selection: str | None = None

        add_all = discord.ui.Button(label="Add All", style=discord.ButtonStyle.success)
        add_all.callback = self._add_all
        custom = discord.ui.Button(label="Custom Selection", style=discord.ButtonStyle.primary)
        custom.callback = self._custom
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger)
        cancel.callback = self._cancel
        for button in (add_all, custom, cancel):
            self.add_item(button)

    async def _add_all(self, interaction: discord.Interaction) -> None:
        self.selection = "all"
        await self.dispose(f"📜 Adding all {self.track_count} tracks…")

    async def _custom(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PlaylistRangeModal(self))

    async def _cancel(self, interaction: discord.Interaction) -> None:
        self.selection = "cancel"
        await self.dispose("Cancelled.")


class PlaylistRangeModal(discord.ui.Modal, title="Select Playlist Range"):
    selection_input = discord.ui.TextInput(
        label="Enter selection",
        placeholder="e.g. '1' or '1-5' or '1,3,5' or '1-3,7,10-12'",
        max_length=100,
    )

    def __init__(self, parent: PlaylistSelectionView) -> None:
        super().__init__()
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.parent.selection = self.selection_input.value
        await interaction.response.defer()
        await self.parent.dispose("📜 Adding selected tracks…")
