FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./discord_bot ./discord_bot
COPY ./.env .
WORKDIR ./discord_bot
CMD ["python", "main.py"]