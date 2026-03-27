from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "OrchAgent"
    API_V1_STR: str = "/api"
    BACKEND_PORT: int = 8002
    # Graph & Loop Limits
    # GRAPH_RECURSION_LIMIT: Hard stop by LangGraph to prevent infinite cycles at any level.
    # TEAM_MAX_DISPATCHES: Soft stop by supervisor to ensure synthesis after N worker calls.
    # The team-level limit is checked first by the supervisor node.
    GRAPH_RECURSION_LIMIT: int = 100
    RESEARCH_TEAM_MAX_DISPATCHES: int = 5
    WRITING_TEAM_MAX_DISPATCHES: int = 5
    DATA_SCIENCE_TEAM_MAX_DISPATCHES: int = 5
    MAIN_AGENT_MODEL: str = "gpt-5.4-mini"
    THREAD_TITLE_MODEL: str = "gpt-5-nano"
    THREAD_SUGGESTIONS_MODEL: str = "gpt-5-nano"
    MEMORY_AGENT_MODEL: str = "gpt-5.4-nano"
    ATTACHMENT_STORAGE_DIR: str = "apps/backend/data/uploads"
    ATTACHMENT_MAX_BYTES: int = 20 * 1024 * 1024
    ATTACHMENT_MAX_FILES_PER_REQUEST: int = 10

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "orchagent"

    STARTUP_MAX_RETRIES: int = 10
    STARTUP_RETRY_DELAY_SECONDS: float = 2.0

    OPENAI_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    AUTH_ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    AUTH_BOOTSTRAP_ADMIN_ENABLED: bool = True
    AUTH_BOOTSTRAP_ADMIN_LOGIN_ID: str = "admin"
    AUTH_BOOTSTRAP_ADMIN_PASSWORD: str = "admin1"
    AUTH_PASSWORD_MIN_LENGTH: int = 4
    AUTH_PASSWORD_REQUIRE_LOWERCASE: bool = True
    AUTH_PASSWORD_REQUIRE_NUMBER: bool = True
    AUTH_PASSWORD_PEPPER: str = ""
    AUTH_TOKEN_PEPPER: str = ""
    AUTH_PBKDF2_ITERATIONS: int = 150000
    AUTH_SESSION_TTL_HOURS: int = 24
    AUTH_SESSION_ABSOLUTE_DAYS: int = 7
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_SESSION_COOKIE_NAME: str = "orch_session"
    AUTH_CSRF_COOKIE_NAME: str = "orch_csrf"
    AUTH_CSRF_HEADER_NAME: str = "X-CSRF-Token"

    @property
    def sync_database_uri(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_uri(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def auth_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.AUTH_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def auth_session_ttl_seconds(self) -> int:
        return self.AUTH_SESSION_TTL_HOURS * 60 * 60

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


settings = Settings()
