# Use official Python 3.10 slim image
FROM python:3.10-slim

# Install ffmpeg and clean up
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set volume for library and .env
VOLUME ["/app/library", "/app/.env", "/app/.urls"]

# Default command
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--help"]
