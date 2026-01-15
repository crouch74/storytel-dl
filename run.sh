#!/bin/bash

# Build the docker image
echo "🐳 Building Storytel Downloader Docker image..."
docker build -t storytel-downloader .

# Create library directory if it doesn't exist
mkdir -p library

# Run the container
# Mount library, .env, and .urls
# Use -it for interactive mode (tqdm and credential prompts)
echo "🚀 Running Storytel Downloader..."
docker run -it --rm \
    -v "$(pwd)/library:/app/library" \
    -v "$(pwd)/.env:/app/.env" \
    -v "$(pwd)/.urls:/app/.urls" \
    storytel-downloader "$@"
