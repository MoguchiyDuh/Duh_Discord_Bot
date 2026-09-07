from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import BaseCog, channel_allowed

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

WEATHER_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Moderate drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    56: ("Light freezing drizzle", "🌧️"),
    57: ("Dense freezing drizzle", "🌧️"),
    61: ("Slight rain", "🌧️"),
    63: ("Moderate rain", "🌧️"),
    65: ("Heavy rain", "⛈️"),
    66: ("Light freezing rain", "🌧️"),
    67: ("Heavy freezing rain", "🌧️"),
    71: ("Slight snowfall", "🌨️"),
    73: ("Moderate snowfall", "🌨️"),
    75: ("Heavy snowfall", "❄️"),
    77: ("Snow grains", "❄️"),
    80: ("Slight rain showers", "🌦️"),
    81: ("Moderate rain showers", "🌧️"),
    82: ("Violent rain showers", "⛈️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with slight hail", "⛈️"),
    99: ("Thunderstorm with heavy hail", "⛈️"),
}


class WeatherCog(BaseCog, commands.Cog):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)

    @staticmethod
    async def _geocode(city: str) -> tuple[float, float, str] | None:
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.get(GEOCODING_URL, params=params) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except aiohttp.ClientError:
            logger.exception("Geocoding request failed")
            return None

        results = data.get("results") or []
        if not results:
            return None
        location = results[0]
        return location["latitude"], location["longitude"], location["name"]

    @app_commands.command(name="weather", description="⛅ Get current weather for a city.")
    @app_commands.describe(city="City name to get weather for.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def get_weather(self, interaction: discord.Interaction, city: str) -> None:
        city = city.strip()
        if not city:
            await interaction.response.send_message(
                "Please provide a valid city name.", ephemeral=True
            )
            return

        await interaction.response.defer()

        geocoded = await self._geocode(city)
        if geocoded is None:
            await interaction.followup.send(f"Could not find location: {city}", ephemeral=True)
            return
        latitude, longitude, location_name = geocoded

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "weather_code"],
            "timezone": "auto",
        }
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.get(FORECAST_URL, params=params) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(
                            "Weather service unavailable.", ephemeral=True
                        )
                        return
                    data = await resp.json()
        except aiohttp.ClientError:
            logger.exception("Weather request failed")
            await interaction.followup.send("Error fetching weather data.", ephemeral=True)
            return

        current = data["current"]
        weather_code = int(current.get("weather_code", -1))
        description, emoji = WEATHER_CODES.get(weather_code, ("Unknown", "🌡️"))

        embed = discord.Embed(
            title=f"Current Weather - {location_name}",
            description=f"{emoji} {description}",
            timestamp=interaction.created_at,
        )
        embed.add_field(name="Temperature", value=f"{current['temperature_2m']}°C", inline=True)
        embed.add_field(name="Humidity", value=f"{current['relative_humidity_2m']}%", inline=True)
        embed.add_field(name="Wind Speed", value=f"{current['wind_speed_10m']} km/h", inline=True)
        embed.set_footer(text="Data from Open-Meteo API")

        await interaction.followup.send(embed=embed)


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(WeatherCog(bot))
