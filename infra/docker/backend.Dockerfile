# Use a lightweight Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Ensure uv doesn't check for updates
ENV UV_NO_CACHE=1

# Copy workspace configuration
COPY pyproject.toml uv.lock ./
COPY apps/backend/pyproject.toml ./apps/backend/
COPY packages/agent-core/pyproject.toml ./packages/agent-core/
COPY packages/agent-tools/pyproject.toml ./packages/agent-tools/
COPY packages/prompt-kit/pyproject.toml ./packages/prompt-kit/

# Install the dependencies for the workspace
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the workspace source code
COPY . .

# Final installation of the project and its members
RUN uv sync --frozen --no-dev

# Set environment variables for the runtime
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/apps/backend:/app/packages/agent-core/src:/app/packages/agent-tools/src:/app/packages/prompt-kit/src"

# Command to run the backend
EXPOSE 8000
WORKDIR /app/apps/backend

# Use 'uv run' to ensure the virtual environment is correctly managed and uvicorn is found
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
