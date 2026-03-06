#!/bin/bash

# Setup environment variables for development
export OPENAI_API_KEY=${OPENAI_API_KEY:-""}
export TAVILY_API_KEY=${TAVILY_API_KEY:-""}

echo "Starting OrchAgent in development mode..."

# Run docker-compose with the provided env vars
docker compose -f infra/compose/docker-compose.yml up --build
