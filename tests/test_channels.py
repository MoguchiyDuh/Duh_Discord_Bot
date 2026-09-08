from __future__ import annotations

import pathlib

from bot.services.channels import COG_CHANNELS

COGS_DIR = pathlib.Path(__file__).resolve().parent.parent / "bot" / "cogs"


def test_every_cog_using_channel_allowed_is_mapped() -> None:
    for path in COGS_DIR.glob("*.py"):
        if path.stem == "__init__":
            continue
        if "channel_allowed(" in path.read_text("utf-8"):
            assert path.stem in COG_CHANNELS, f"{path.stem} missing from COG_CHANNELS"
