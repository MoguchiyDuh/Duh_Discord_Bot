# import json
# import discord
# from discord.ext import commands
# from discord import app_commands
# import re
# import os
# import logging

# from src.services.yt_source import YTSource
# from .music import MusicCog

# logging.basicConfig(level=logging.ERROR)
# logger = logging.getLogger("discord")
# logger.setLevel(logging.ERROR)

# PLAYLISTS_PATH = "playlists.json"


# class PlaylistGroup(app_commands.Group):
#     """Command group for managing playlists."""

#     def __init__(self, bot: commands.Bot):
#         super().__init__(name="playlist", description="Manage your playlists.")
#         self.playlists = self.__load_playlists()

#     def __load_playlists(self) -> dict[int, dict[str, list[str]]]:
#         """Load playlists from file."""
#         if os.path.isfile(PLAYLISTS_PATH):
#             with open(PLAYLISTS_PATH, "r") as f:
#                 return json.load(f)
#         return {}

#     def __save_playlists(self):
#         """Save playlists to file."""
#         with open(PLAYLISTS_PATH, "w") as f:
#             json.dump(self.playlists, f, indent=4)

#     @app_commands.command(name="list", description="List all playlists on this server")
#     async def list_playlist(self, interaction: discord.Interaction):
#         """List all playlists on this server."""
#         guild_id = interaction.guild_id
#         if not self.playlists:
#             await interaction.response.send_message(
#                 "No saved playlists found. Create your own by with `playlist create <name>`"
#             )
#             return

#         embed = discord.Embed(
#             title="Saved playlists",
#             description="\n".join(
#                 [
#                     f"{i}. {playlist} - {len(self.playlists[guild_id][playlist])} tracks"
#                     for i, playlist in enumerate(self.playlists[guild_id], start=1)
#                 ]
#             ),
#             color=discord.Color.blue(),
#         )
#         await interaction.response.send_message(embed=embed)

#     @app_commands.command(name="tracks", description="List all tracks in a playlist")
#     async def list_tracks(self, interaction: discord.Interaction, name: str):
#         "Show all tracks in a platlist"
#         guild_id = interaction.guild_id
#         if not self.playlists:
#             await interaction.response.send_message(
#                 "No saved playlists found. Create your own by with `playlist create <name>`"
#             )
#             return

#         embed = discord.Embed(
#             title=f"{name} - {len(self.playlists[guild_id][name])} songs",
#             description="\n".join(
#                 [
#                     f"{i}. {track}"
#                     for i, track in enumerate(self.playlists[guild_id][name], start=1)
#                 ]
#             ),
#             color=discord.Color.blue(),
#         )
#         await interaction.response.send_message(embed=embed)

#     @app_commands.command(name="create", description="Create a new playlist")
#     async def create_playlist(self, interaction: discord.Interaction, name: str):
#         """Create a new playlist."""
#         guild_id = interaction.guild_id
#         if name in self.playlists:
#             await interaction.response.send_message("Playlist already exists.")
#             return

#         if not self.playlists.get(interaction.guild_id):
#             self.playlists[guild_id] = {}

#         self.playlists[guild_id][name] = []
#         self.__save_playlists()
#         await interaction.response.send_message(f"Created playlist {name}.")

#     @app_commands.command(name="delete", description="Delete a playlist")
#     async def delete_playlist(
#         self,
#         interaction: discord.Interaction,
#         name: str,
#     ):
#         """Delete a playlist."""
#         guild_id = interaction.guild_id
#         if name not in self.playlists:
#             await interaction.response.send_message("Playlist does not exist.")
#             return
#         del self.playlists[guild_id][name]
#         self.__save_playlists()
#         await interaction.response.send_message(f"Deleted playlist {name}.")

#     @app_commands.command(name="rename", description="Rename a playlist")
#     async def rename_playlist(
#         self,
#         interaction: discord.Interaction,
#         name: str,
#         new_name: str,
#     ):
#         """Rename a playlist."""
#         if name not in self.playlists:
#             await interaction.response.send_message("Playlist does not exist.")
#             return
#         if new_name in self.playlists[interaction.guild_id]:
#             await interaction.response.send_message(
#                 f"A playlist with the name {new_name} already exists."
#             )
#             return

#         self.playlists[interaction.guild_id][new_name] = self.playlists[
#             interaction.guild_id
#         ].pop(name)
#         self.__save_playlists()
#         await interaction.response.send_message(
#             f"Renamed playlist {name} to {new_name}."
#         )

#     @app_commands.command(name="add-track", description="Add a track to a playlist")
#     async def add_to_playlist(
#         self,
#         interaction: discord.Interaction,
#         name: str,
#         track_url: str,
#     ):
#         """Add a track to a playlist."""
#         await interaction.response.defer()
#         if name not in self.playlists[interaction.guild_id]:
#             await interaction.followup.send("Playlist does not exist.")
#             return

#         source = YTSource()
#         track = await source.fetch_track_by_url(url=track_url)
#         if track is None:
#             await interaction.followup.send("Track not found.")
#             return

#         self.playlists[interaction.guild_id][name].append(track_url)
#         self.__save_playlists()

#         response_text = str(track)
#         thumbnail = track.thumbnail
#         embed = discord.Embed(
#             title=f"Added to the playlist {name}",
#             description=response_text,
#             color=discord.Color.blue(),
#         )
#         if thumbnail:
#             embed.set_thumbnail(url=thumbnail)
#         await interaction.followup.send(embed=embed)

#     @app_commands.command(
#         name="remove-track", description="Remove a track from a playlist"
#     )
#     async def remove_from_playlist(
#         self,
#         interaction: discord.Interaction,
#         name: str,
#         track_id: int,
#     ):
#         """Remove a track from a playlist."""
#         guild_id = interaction.guild_id
#         if name not in self.playlists[guild_id]:
#             await interaction.response.send_message("Playlist does not exist.")
#             return

#         if 0 > track_id - 1 > len(self.playlists[guild_id][name]):
#             await interaction.response.send_message("Track not found in playlist.")
#             return

#         del self.playlists[guild_id][name][track_id - 1]
#         if not self.playlists[guild_id][name]:
#             del self.playlists[guild_id][name]
#         self.__save_playlists()
#         await interaction.response.send_message(
#             f"Removed {self.playlists[guild_id][name][track_id - 1]} from the playlist {name}."
#         )

#     # FIXME:
#     # @app_commands.command(name="play", description="Play a playlist")
#     # async def play_playlist(self, interaction: discord.Interaction, name: str):
#     #     """Play a playlist."""
#     #     guild_id = interaction.guild_id
#     #     if name not in self.playlists[guild_id]:
#     #         await interaction.response.send_message("Playlist does not exist.")
#     #         return

#     #     for track in self.playlists[guild_id]:
#     #         play somehow


# class PlaylistCog(commands.Cog):
#     def __init__(self, bot: commands.Bot):
#         self.bot = bot
#         self.bot.tree.add_command(PlaylistGroup(bot))


# async def setup(bot: commands.Bot):
#     await bot.add_cog(PlaylistCog(bot))
