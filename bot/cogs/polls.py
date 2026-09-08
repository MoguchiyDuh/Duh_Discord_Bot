from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import BaseCog, channel_allowed

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)

POLL_EMOJI = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")

BAR_WIDTH = 10


def _fmt_seconds(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{sec:02}"
    return f"{minutes}:{sec:02}"


class Poll:
    def __init__(
        self,
        question: str,
        choices: list[str],
        *,
        minutes: int,
        multi: bool,
        requester: str,
    ) -> None:
        self.question = question
        self.choices = choices
        self.multi = multi
        self.requester = requester
        self.ends_at = time.monotonic() + minutes * 60
        self.votes: dict[int, set[int]] = {}
        self.message: discord.abc.Message | None = None
        self.view: PollView | None = None
        self.finalized = False
        self._edit_lock = asyncio.Lock()

    def vote(self, user_id: int, index: int) -> None:
        current = self.votes.get(user_id, set())
        if index in current:
            current.discard(index)
        elif self.multi:
            current.add(index)
        else:
            current = {index}
        if current:
            self.votes[user_id] = current
        else:
            self.votes.pop(user_id, None)

    def tally(self) -> list[int]:
        counts = [0] * len(self.choices)
        for picked in self.votes.values():
            for index in picked:
                counts[index] += 1
        return counts

    def _bars(self, counts: list[int]) -> list[str]:
        peak = max(counts, default=0)
        bars: list[str] = []
        for count in counts:
            filled = round(BAR_WIDTH * count / peak) if peak else 0
            bars.append("▰" * filled + "▱" * (BAR_WIDTH - filled))
        return bars

    def render(self, *, final: bool = False) -> discord.Embed:
        counts = self.tally()
        total = sum(counts)
        voters = len(self.votes)
        bars = self._bars(counts)
        if final:
            title = f"🏁 Poll ended — {self.question}"
            peak = max(counts, default=0)
            winners = [self.choices[i] for i, c in enumerate(counts) if c == peak and peak > 0]
            head = "🏆 " + " • ".join(w[:80] for w in winners) if winners else "🤷 No votes"
            description = head + "\n"
            color = discord.Color.gold()
            footer = f"Final results • {total} vote(s)"
        else:
            title = f"📊 {self.question}"
            description = ""
            color = discord.Color.blurple()
            remaining = _fmt_seconds(self.ends_at - time.monotonic())
            mode = "multi-choice" if self.multi else "one vote per person"
            footer = f"Ends in {remaining} • {voters} voter(s) • {mode} • by {self.requester}"
        for i, choice in enumerate(self.choices):
            pct = round(100 * counts[i] / total) if total else 0
            description += (
                f"\n{POLL_EMOJI[i]} **{choice[:80]}** — {counts[i]} ({pct}%)\n"
                f"-# `{bars[i]}`"
            )
        embed = discord.Embed(title=title[:256], description=description[:4000], color=color)
        embed.set_footer(text=footer)
        return embed

    async def refresh(self) -> None:
        if self.message is None or self.finalized:
            return
        async with self._edit_lock:
            try:
                await self.message.edit(embed=self.render())
            except discord.NotFound:
                self.finalized = True
            except discord.HTTPException as exc:
                logger.warning("Poll edit failed: %s", exc)

    async def finalize(self) -> None:
        if self.finalized:
            return
        self.finalized = True
        if self.view is not None:
            for child in self.view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embed=self.render(final=True), view=self.view)
            except discord.HTTPException as exc:
                logger.warning("Poll finalize failed: %s", exc)

    async def run(self) -> None:
        try:
            while not self.finalized:
                remaining = self.ends_at - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(5.0, remaining))
                await self.refresh()
            await self.finalize()
        except asyncio.CancelledError:
            raise


class PollView(discord.ui.View):
    def __init__(self, poll: Poll) -> None:
        super().__init__(timeout=None)
        self.poll = poll
        poll.view = self
        for i, choice in enumerate(poll.choices):
            button = discord.ui.Button(
                label=choice[:80],
                emoji=POLL_EMOJI[i],
                style=discord.ButtonStyle.secondary,
                row=i // 5,
            )
            button.callback = self._make_callback(i)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            self.poll.vote(interaction.user.id, index)
            await self.poll.refresh()

        return callback


class PollsCog(BaseCog, commands.Cog):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)

    @app_commands.command(name="poll", description="📊 Create a poll with a live countdown")
    @app_commands.describe(
        question="Poll question",
        choices="Comma-separated options (2-10), e.g. yes, no, maybe",
        minutes="Minutes until the poll ends (1-1440)",
        multi="Allow selecting multiple options",
    )
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        choices: str,
        minutes: app_commands.Range[int, 1, 1440] = 5,
        multi: bool = False,
    ) -> None:
        options = [c.strip() for c in choices.split(",") if c.strip()]
        if len(options) < 2:
            await interaction.response.send_message(
                "❌ Provide at least 2 choices, comma-separated.", ephemeral=True
            )
            return
        if len(options) > 10:
            await interaction.response.send_message(
                "❌ Too many choices — 10 max.", ephemeral=True
            )
            return
        poll = Poll(
            question.strip()[:256],
            options,
            minutes=minutes,
            multi=multi,
            requester=interaction.user.display_name,
        )
        view = PollView(poll)
        await interaction.response.send_message(embed=poll.render(), view=view)
        poll.message = await interaction.original_response()
        self.bot.loop.create_task(poll.run())
        logger.info(
            "Poll started in #%s by %s: %r (%d options, %d min)",
            getattr(interaction.channel, "name", "unknown"),
            interaction.user,
            poll.question,
            len(options),
            minutes,
        )


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(PollsCog(bot))
