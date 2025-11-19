import aiohttp
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from . import EMBED_COLOR, BaseCog, channel_allowed

if TYPE_CHECKING:
    from . import MyBot


class WeatherCog(BaseCog, commands.Cog):
    """Weather commands using Open-Meteo API (no key required)."""

    def __init__(self, bot: "MyBot"):
        super().__init__(bot)
        self.bot = bot
        self.logger = bot.logger.getChild("weather")
        self.geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.weather_url = "https://api.open-meteo.com/v1/forecast"

    async def _get_coordinates(self, city: str) -> Optional[tuple]:
        """Get coordinates for a city using Open-Meteo geocoding."""
        try:
            params = {"name": city, "count": 1, "language": "en", "format": "json"}
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.geocoding_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("results"):
                            location = data["results"][0]
                            return (
                                location["latitude"],
                                location["longitude"],
                                location["name"],
                            )
            return None
        except Exception as e:
            self.logger.error(f"Geocoding error: {e}")
            return None

    @app_commands.command(
        name="weather", description="⛅ Get current weather for a city."
    )
    @app_commands.describe(city="City name to get weather for.")
    @channel_allowed(__file__)
    async def get_weather(self, interaction: discord.Interaction, city: str):
        """Get current weather using Open-Meteo API (free, no key required)."""
        if not city.strip():
            await interaction.response.send_message(
                "Please provide a valid city name.", ephemeral=True
            )
            return

        await interaction.response.defer()

        coords = await self._get_coordinates(city.strip())
        if not coords:
            await interaction.followup.send(
                f"Could not find location: {city}", ephemeral=True
            )
            return

        lat, lon, location_name = coords

        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "weather_code",
                ],
                "timezone": "auto",
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.weather_url, params=params) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(
                            "Weather service unavailable.", ephemeral=True
                        )
                        return

                    data = await resp.json()
                    current = data["current"]

                    embed = discord.Embed(
                        title=f"Current Weather - {location_name}",
                        color=EMBED_COLOR,
                        timestamp=interaction.created_at,
                    )

                    temp = current["temperature_2m"]
                    humidity = current["relative_humidity_2m"]
                    wind_speed = current["wind_speed_10m"]

                    embed.add_field(name="Temperature", value=f"{temp}°C", inline=True)
                    embed.add_field(name="Humidity", value=f"{humidity}%", inline=True)
                    embed.add_field(
                        name="Wind Speed", value=f"{wind_speed} km/h", inline=True
                    )

                    embed.set_footer(text="Data from Open-Meteo API")

                    await interaction.followup.send(embed=embed)

        except Exception as e:
            self.logger.error(f"Weather API error: {e}")
            await interaction.followup.send(
                "Error fetching weather data.", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WeatherCog(bot))
