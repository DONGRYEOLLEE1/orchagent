# 🤖 OrchAgent: Hierarchical Multi-Agent Platform

Welcome to **OrchAgent**, an enterprise-grade hierarchical multi-agent platform designed for complex task decomposition and real-time reasoning visualization.

## 🏗️ Project Overview

OrchAgent utilizes a **Multi-Supervisor architecture** (`Head Supervisor -> Team Supervisor -> Worker`) built on **LangGraph** and **FastAPI**. It features a modern **Agentic UI** with glassmorphism, providing real-time streaming of agent reasoning and tool execution.

### Key Components
- **`apps/backend`**: FastAPI server hosting the LangGraph workflow engine and telemetry services.
- **`apps/frontend`**: Next.js 16 dashboard for interacting with the agents.
- **`packages/agent-core`**: Core abstractions for hierarchical orchestration and state management.
- **`packages/agent-tools`**: Shared tools for vision analysis, web searching, and scraping.
- **`packages/prompt-kit`**: Centralized management of system prompts.
- **`infra/`**: Docker-based infrastructure and deployment scripts.

### Core Technologies
- **Backend**: Python 3.12, FastAPI, LangGraph, SQLAlchemy, PostgreSQL, `uv` (package manager).
- **Frontend**: Next.js 16, React 19, TailwindCSS 4, TypeScript.
- **Infrastructure**: Docker, Docker Compose.

---

## 🚀 Building and Running

### 🐳 Quick Start (Docker)
The easiest way to get started is using the provided development script:
```bash
./infra/scripts/start-dev.sh
```
*Note: Ensure `OPENAI_API_KEY` and `TAVILY_API_KEY` are set in `apps/backend/.env`.*

### 🐍 Backend Development (Local)
1. **Navigate**: `cd apps/backend`
2. **Install**: `uv sync` (includes workspace packages)
3. **Run**: `uv run uvicorn main:app --reload --port 8000`
4. **Test**: `uv run pytest tests/ -v`

### ⚛️ Frontend Development (Local)
1. **Navigate**: `cd apps/frontend`
2. **Install**: `npm install`
3. **Run**: `npm run dev` (starts on port 3000)
4. **Lint**: `npm run lint`

---

## 🛠️ Development Conventions

### 🛡️ Code Quality & Safety
We use **pre-commit** hooks to ensure code integrity. Before committing, the following checks are run:
- **Python**: 
  - **Linter/Formatter**: `ruff` (with auto-fix)
  - **Type Checker**: `ty` (lightning-fast checker via `uvx ty check`)
- **Frontend**: 
  - **Linter**: `eslint`

### 📋 Architectural Patterns
- **Hierarchical Teams**: Logic is split into specialized teams (Vision, Research, Writing), each managed by its own supervisor.
- **KST-Based Telemetry**: All business telemetry and logging are strictly recorded in **Korean Standard Time (KST)**.
- **Data Persistence**: Detailed session logs are stored in `.jsonl` files (via `LoggingService`), separate from the SQL-based tracing DB.

### 🧪 Testing
- Backend tests are located in `apps/backend/tests/`.
- Use `pytest` for all backend testing.
- Integration tests for LLMs are available but require API keys.

---
*Maintained by the OrchAgent Team.*
