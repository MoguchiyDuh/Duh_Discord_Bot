"""HTTP API server for MCP integration."""

import asyncio
from typing import TYPE_CHECKING, Dict, List, Optional

from aiohttp import web

if TYPE_CHECKING:
    from bot import MyBot


class BotAPIServer:
    """HTTP API server for external bot control via MCP."""

    def __init__(self, bot: "MyBot", host: str = "127.0.0.1", port: int = 8765):
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self._setup_routes()

    def _setup_routes(self):
        """Configure API routes."""
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/guilds", self.get_guilds)
        self.app.router.add_get("/guilds/{guild_id}/player", self.get_player_status)
        self.app.router.add_post("/guilds/{guild_id}/search", self.search_music)
        self.app.router.add_post("/guilds/{guild_id}/play", self.add_to_queue)
        self.app.router.add_post("/guilds/{guild_id}/skip", self.skip_track)
        self.app.router.add_post("/guilds/{guild_id}/clear", self.clear_queue)
        self.app.router.add_post("/guilds/{guild_id}/pause", self.pause_playback)
        self.app.router.add_post("/guilds/{guild_id}/resume", self.resume_playback)
        self.app.router.add_post("/guilds/{guild_id}/shuffle", self.shuffle_queue)

    async def start(self):
        """Start the API server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        self.bot.logger.info(f"API server running on {self.host}:{self.port}")

    async def stop(self):
        """Stop the API server."""
        if self.runner:
            await self.runner.cleanup()
            self.bot.logger.info("API server stopped")

    async def health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "ok", "bot_ready": self.bot.is_ready()})

    async def get_guilds(self, request: web.Request) -> web.Response:
        """Get list of guilds the bot is in."""
        guilds = [
            {"id": str(guild.id), "name": guild.name} for guild in self.bot.guilds
        ]
        return web.json_response({"guilds": guilds})

    async def get_player_status(self, request: web.Request) -> web.Response:
        """Get player status for a guild."""
        guild_id = int(request.match_info["guild_id"])
        music_cog = self.bot.get_cog("music")

        if not music_cog:
            return web.json_response({"error": "Music cog not loaded"}, status=500)

        player = music_cog.players.get(guild_id)
        if not player:
            return web.json_response(
                {
                    "connected": False,
                    "state": "idle",
                    "current": None,
                    "queue": [],
                    "loop": False,
                }
            )

        current = None
        if player.current_item:
            current = {
                "title": player.current_item.title,
                "url": player.current_item.url,
                "author": player.current_item.author,
                "duration": player.current_item.formatted_duration,
            }

        queue = [
            {
                "title": track.title,
                "url": track.url,
                "author": track.author,
                "duration": track.formatted_duration,
            }
            for track in player.queue
        ]

        return web.json_response(
            {
                "connected": bool(player.voice_client),
                "state": player.state.name.lower(),
                "current": current,
                "queue": queue,
                "queue_length": len(player.queue),
                "loop": player.loop,
            }
        )

    async def search_music(self, request: web.Request) -> web.Response:
        """Search for music."""
        guild_id = int(request.match_info["guild_id"])
        data = await request.json()
        query = data.get("query")

        if not query:
            return web.json_response({"error": "Query required"}, status=400)

        from bot.services.yt_source import TrackFetcher

        try:
            results = await TrackFetcher.fetch_track_by_name(query)
            if not results:
                return web.json_response({"results": []})

            search_results = [
                {"title": title, "url": url} for title, url in results.items()
            ]
            return web.json_response({"results": search_results})
        except Exception as e:
            self.bot.logger.error(f"Search error: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def add_to_queue(self, request: web.Request) -> web.Response:
        """Add track to queue."""
        guild_id = int(request.match_info["guild_id"])
        data = await request.json()
        url = data.get("url")
        query = data.get("query")

        if not url and not query:
            return web.json_response(
                {"error": "Either url or query required"}, status=400
            )

        music_cog = self.bot.get_cog("music")
        if not music_cog:
            return web.json_response({"error": "Music cog not loaded"}, status=500)

        player = music_cog.players.get(guild_id)
        if not player or not player.voice_client:
            return web.json_response(
                {"error": "Bot not in voice channel"}, status=400
            )

        from bot.services.yt_source import TrackFetcher

        try:
            if url:
                track = await TrackFetcher.fetch_track_by_url(url)
            else:
                results = await TrackFetcher.fetch_track_by_name(query)
                if not results:
                    return web.json_response(
                        {"error": "No results found"}, status=404
                    )
                first_url = next(iter(results.values()))
                track = await TrackFetcher.fetch_track_by_url(first_url)

            if not track:
                return web.json_response({"error": "Failed to fetch track"}, status=500)

            player.queue.append(track)
            self.bot.logger.info(f"API: Added track to queue: {track.title}")

            # If not playing, start playback
            if not player.is_active and player.queue:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    # Create a mock interaction for _play_next
                    class MockChannel:
                        async def send(self, **kwargs):
                            pass

                    class MockInteraction:
                        def __init__(self, guild, channel):
                            self.guild = guild
                            self.channel = channel

                    mock_interaction = MockInteraction(
                        guild, guild.system_channel or MockChannel()
                    )
                    await music_cog._play_next(mock_interaction)

            return web.json_response(
                {
                    "success": True,
                    "track": {
                        "title": track.title,
                        "url": track.url,
                        "author": track.author,
                    },
                }
            )
        except Exception as e:
            self.bot.logger.error(f"Add to queue error: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def skip_track(self, request: web.Request) -> web.Response:
        """Skip current or specific track."""
        guild_id = int(request.match_info["guild_id"])
        data = await request.json()
        index = data.get("index")

        music_cog = self.bot.get_cog("music")
        if not music_cog:
            return web.json_response({"error": "Music cog not loaded"}, status=500)

        player = music_cog.players.get(guild_id)
        if not player or not player.is_active:
            return web.json_response({"error": "Nothing playing"}, status=400)

        try:
            if index is None:
                skipped = player.skip_current()
                skipped_tracks = [skipped] if skipped else []
            else:
                skipped_tracks = player.skip_index(int(index))

            return web.json_response(
                {
                    "success": True,
                    "skipped": len(skipped_tracks),
                    "tracks": [
                        {"title": t.title, "url": t.url}
                        for t in skipped_tracks
                        if t
                    ],
                }
            )
        except Exception as e:
            self.bot.logger.error(f"Skip error: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def clear_queue(self, request: web.Request) -> web.Response:
        """Clear the queue."""
        guild_id = int(request.match_info["guild_id"])

        music_cog = self.bot.get_cog("music")
        if not music_cog:
            return web.json_response({"error": "Music cog not loaded"}, status=500)

        player = music_cog.players.get(guild_id)
        if not player:
            return web.json_response({"error": "No player found"}, status=400)

        queue_size = len(player.queue)
        player.queue.clear()
        self.bot.logger.info(f"API: Cleared queue ({queue_size} tracks)")

        return web.json_response({"success": True, "cleared": queue_size})

    async def pause_playback(self, request: web.Request) -> web.Response:
        """Pause playback."""
        guild_id = int(request.match_info["guild_id"])

        music_cog = self.bot.get_cog("music")
        if not music_cog:
            return web.json_response({"error": "Music cog not loaded"}, status=500)

        player = music_cog.players.get(guild_id)
        if not player or not player.voice_client:
            return web.json_response({"error": "Not playing"}, status=400)

        if player.voice_client.is_playing():
            player.voice_client.pause()
            from bot.cogs.music import PlayerState

            player.state = PlayerState.PAUSED
            return web.json_response({"success": True, "state": "paused"})
        else:
            return web.json_response({"error": "Already paused"}, status=400)

    async def resume_playback(self, request: web.Request) -> web.Response:
        """Resume playback."""
        guild_id = int(request.match_info["guild_id"])

        music_cog = self.bot.get_cog("music")
        if not music_cog:
            return web.json_response({"error": "Music cog not loaded"}, status=500)

        player = music_cog.players.get(guild_id)
        if not player or not player.voice_client:
            return web.json_response({"error": "Not playing"}, status=400)

        if player.voice_client.is_paused():
            player.voice_client.resume()
            from bot.cogs.music import PlayerState

            player.state = PlayerState.PLAYING
            return web.json_response({"success": True, "state": "playing"})
        else:
            return web.json_response({"error": "Not paused"}, status=400)

    async def shuffle_queue(self, request: web.Request) -> web.Response:
        """Shuffle the queue."""
        guild_id = int(request.match_info["guild_id"])

        music_cog = self.bot.get_cog("music")
        if not music_cog:
            return web.json_response({"error": "Music cog not loaded"}, status=500)

        player = music_cog.players.get(guild_id)
        if not player or not player.queue:
            return web.json_response({"error": "Queue empty"}, status=400)

        player.shuffle_queue()
        self.bot.logger.info(f"API: Shuffled queue")

        return web.json_response({"success": True, "queue_length": len(player.queue)})
