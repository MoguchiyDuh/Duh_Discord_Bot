import asyncio
import discord
import yt_dlp as youtube_dl


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")

    ytdl_format_options = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

    ffmpeg_options = {
        "options": "-vn -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    }

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        try:
            loop = loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: cls.ytdl.extract_info(url, download=not stream)
            )

            if "entries" in data:

                data = data["entries"][0]

            filename = data["url"] if stream else cls.ytdl.prepare_filename(data)
            return cls(
                discord.FFmpegPCMAudio(filename, **cls.ffmpeg_options), data=data
            )
        except Exception as e:
            print(e)
