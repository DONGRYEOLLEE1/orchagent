#!/bin/bash

# Setup environment variables for development
export OPENAI_API_KEY=${OPENAI_API_KEY:-""}
export TAVILY_API_KEY=${TAVILY_API_KEY:-""}

echo "Starting OrchAgent in development mode with bind mounts and autoreload..."
echo "Code changes under apps/ and packages/ will hot-reload inside the containers."
echo "Rebuild is only required when dependencies or Dockerfiles change."

# Run docker-compose with the provided env vars
docker compose -f infra/compose/docker-compose.yml up --build
