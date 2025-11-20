#!/usr/bin/env python3
"""MCP server for Discord music bot control."""

import asyncio
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent


BOT_API_URL = os.getenv("DISCORD_BOT_API_URL", "http://127.0.0.1:8765")


app = Server("discord-bot")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Discord bot control tools."""
    return [
        Tool(
            name="list_guilds",
            description="List all Discord servers (guilds) the bot is connected to",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_player_status",
            description="Get current player status for a guild including queue and current track",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    }
                },
                "required": ["guild_id"],
            },
        ),
        Tool(
            name="search_music",
            description="Search for music on YouTube by query",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (song name, artist, etc.)",
                    },
                },
                "required": ["guild_id", "query"],
            },
        ),
        Tool(
            name="add_to_queue",
            description="Add a track to the queue by URL or search query",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    },
                    "url": {
                        "type": "string",
                        "description": "Direct YouTube/SoundCloud URL (optional if query provided)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query to add first result (optional if url provided)",
                    },
                },
                "required": ["guild_id"],
            },
        ),
        Tool(
            name="skip_track",
            description="Skip the current track or a specific track by index (0=current, 1=next in queue, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    },
                    "index": {
                        "type": "integer",
                        "description": "Track index to skip (0=current, 1+=queue position, omit to skip current)",
                    },
                },
                "required": ["guild_id"],
            },
        ),
        Tool(
            name="clear_queue",
            description="Clear all tracks from the queue",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    }
                },
                "required": ["guild_id"],
            },
        ),
        Tool(
            name="pause_playback",
            description="Pause the current playback",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    }
                },
                "required": ["guild_id"],
            },
        ),
        Tool(
            name="resume_playback",
            description="Resume paused playback",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    }
                },
                "required": ["guild_id"],
            },
        ),
        Tool(
            name="shuffle_queue",
            description="Shuffle the current queue",
            inputSchema={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "Discord guild/server ID",
                    }
                },
                "required": ["guild_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    async with httpx.AsyncClient(base_url=BOT_API_URL, timeout=30.0) as client:
        try:
            if name == "list_guilds":
                response = await client.get("/guilds")
                response.raise_for_status()
                data = response.json()
                guilds = data.get("guilds", [])
                if not guilds:
                    return [TextContent(type="text", text="No guilds found")]
                guild_list = "\n".join(
                    f"• {g['name']} (ID: {g['id']})" for g in guilds
                )
                return [
                    TextContent(type="text", text=f"Connected guilds:\n{guild_list}")
                ]

            elif name == "get_player_status":
                guild_id = arguments["guild_id"]
                response = await client.get(f"/guilds/{guild_id}/player")
                response.raise_for_status()
                data = response.json()

                status_lines = [
                    f"Connected: {data['connected']}",
                    f"State: {data['state']}",
                    f"Loop: {data['loop']}",
                ]

                if data.get("current"):
                    current = data["current"]
                    status_lines.append(
                        f"\nNow Playing: {current['title']} by {current.get('author', 'Unknown')}"
                    )
                    status_lines.append(f"Duration: {current.get('duration', 'N/A')}")
                    status_lines.append(f"URL: {current['url']}")

                status_lines.append(f"\nQueue: {data['queue_length']} tracks")
                if data.get("queue"):
                    status_lines.append("\nNext up:")
                    for i, track in enumerate(data["queue"][:5], 1):
                        status_lines.append(f"  {i}. {track['title']}")
                    if data["queue_length"] > 5:
                        status_lines.append(
                            f"  ... and {data['queue_length'] - 5} more"
                        )

                return [TextContent(type="text", text="\n".join(status_lines))]

            elif name == "search_music":
                guild_id = arguments["guild_id"]
                query = arguments["query"]
                response = await client.post(
                    f"/guilds/{guild_id}/search", json={"query": query}
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    return [TextContent(type="text", text="No results found")]

                result_lines = ["Search results:"]
                for i, result in enumerate(results, 1):
                    result_lines.append(f"{i}. {result['title']}")
                    result_lines.append(f"   URL: {result['url']}")

                return [TextContent(type="text", text="\n".join(result_lines))]

            elif name == "add_to_queue":
                guild_id = arguments["guild_id"]
                payload = {}
                if "url" in arguments:
                    payload["url"] = arguments["url"]
                if "query" in arguments:
                    payload["query"] = arguments["query"]

                response = await client.post(f"/guilds/{guild_id}/play", json=payload)
                response.raise_for_status()
                data = response.json()

                track = data.get("track", {})
                return [
                    TextContent(
                        type="text",
                        text=f"Added to queue: {track.get('title', 'Unknown')} by {track.get('author', 'Unknown')}",
                    )
                ]

            elif name == "skip_track":
                guild_id = arguments["guild_id"]
                payload = {}
                if "index" in arguments:
                    payload["index"] = arguments["index"]

                response = await client.post(f"/guilds/{guild_id}/skip", json=payload)
                response.raise_for_status()
                data = response.json()

                skipped_count = data.get("skipped", 0)
                tracks = data.get("tracks", [])
                if tracks:
                    track_names = ", ".join(t["title"] for t in tracks)
                    return [
                        TextContent(
                            type="text", text=f"Skipped {skipped_count} track(s): {track_names}"
                        )
                    ]
                return [TextContent(type="text", text=f"Skipped {skipped_count} track(s)")]

            elif name == "clear_queue":
                guild_id = arguments["guild_id"]
                response = await client.post(f"/guilds/{guild_id}/clear")
                response.raise_for_status()
                data = response.json()

                return [
                    TextContent(
                        type="text", text=f"Cleared {data.get('cleared', 0)} tracks from queue"
                    )
                ]

            elif name == "pause_playback":
                guild_id = arguments["guild_id"]
                response = await client.post(f"/guilds/{guild_id}/pause")
                response.raise_for_status()
                return [TextContent(type="text", text="Playback paused")]

            elif name == "resume_playback":
                guild_id = arguments["guild_id"]
                response = await client.post(f"/guilds/{guild_id}/resume")
                response.raise_for_status()
                return [TextContent(type="text", text="Playback resumed")]

            elif name == "shuffle_queue":
                guild_id = arguments["guild_id"]
                response = await client.post(f"/guilds/{guild_id}/shuffle")
                response.raise_for_status()
                data = response.json()
                return [
                    TextContent(
                        type="text",
                        text=f"Shuffled queue ({data.get('queue_length', 0)} tracks)",
                    )
                ]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}"
            try:
                error_data = e.response.json()
                error_msg += f": {error_data.get('error', str(e))}"
            except Exception:
                error_msg += f": {str(e)}"
            return [TextContent(type="text", text=f"Error: {error_msg}")]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
