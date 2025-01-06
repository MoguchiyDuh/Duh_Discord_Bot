FROM python:3.10-slim
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "-m", "bot"]