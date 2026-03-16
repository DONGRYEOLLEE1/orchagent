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

### 🏗️ Engineering Mandates (필수 준수 사항)
- **Centralized Prompts**: 모든 시스템 프롬프트는 반드시 `packages/prompt-kit` 패키지 내에서 관리되어야 합니다. 소스 코드 내에 프롬프트 문자열을 하드코딩하는 것은 엄격히 금지됩니다.
- **Agent Factory**: 워커 에이전트 생성 시 반드시 `langchain.agents.create_agent`를 사용하십시오. `langgraph.prebuilt.create_react_agent`는 Deprecated 되었으므로 사용을 금지합니다.

### 📋 Architectural Patterns
- **Hierarchical Teams**: Logic is split into specialized teams (Vision, Research, Writing), each managed by its own supervisor.
- **KST-Based Telemetry**: All business telemetry and logging are strictly recorded in **Korean Standard Time (KST)**.
- **Data Persistence**: Detailed session logs are stored in `.jsonl` files (via `LoggingService`), separate from the SQL-based tracing DB.

### 📝 Plan Management (계획 관리)
- **Progress Tracking**: `plans/*` 폴더 내의 구현 목표를 실행할 때, 해당 마크다운 파일의 TODO 리스트(`- [ ]`)를 단계별로 체크(`- [x]`)하여 항상 최신 진행 상황을 반영해야 합니다.
- **Dynamic Updates**: 구현 과정에서 계획의 수정이나 추가 단계가 필요한 경우, 즉시 해당 계획 파일을 업데이트하여 설계와 구현의 일관성을 유지합니다.

### 🧪 Testing
- Backend tests are located in `apps/backend/tests/`.
- Use `pytest` for all backend testing.
- Integration tests for LLMs are available but require API keys.

### Tone & Style
- 반드시 한국어로 답변

---
*Maintained by the OrchAgent Team.*
