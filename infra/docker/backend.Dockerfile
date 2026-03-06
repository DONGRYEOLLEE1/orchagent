# Use a lightweight Python image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy only pyproject.toml and uv.lock to cache dependencies
COPY pyproject.toml uv.lock ./
COPY apps/backend/pyproject.toml ./apps/backend/
COPY packages/agent-core/pyproject.toml ./packages/agent-core/
COPY packages/agent-tools/pyproject.toml ./packages/agent-tools/
COPY packages/prompt-kit/pyproject.toml ./packages/prompt-kit/

# Install the dependencies (without copying the full source)
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the workspace source code
COPY . .

# Final installation of the project
RUN uv sync --frozen --no-dev

# --- Runner Stage ---
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy the environment from the builder
COPY --from=builder /app /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/apps/backend:/app/packages/agent-core/src:/app/packages/agent-tools/src:/app/packages/prompt-kit/src"

# Command to run the backend
EXPOSE 8000
WORKDIR /app/apps/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
