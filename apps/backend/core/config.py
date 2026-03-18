from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "OrchAgent"
    API_V1_STR: str = "/api"
    BACKEND_PORT: int = 8002
    GRAPH_RECURSION_LIMIT: int = 100
    RESEARCH_TEAM_MAX_DISPATCHES: int = 5
    WRITING_TEAM_MAX_DISPATCHES: int = 3

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "orchagent"

    STARTUP_MAX_RETRIES: int = 10
    STARTUP_RETRY_DELAY_SECONDS: float = 2.0

    OPENAI_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    @property
    def sync_database_uri(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_uri(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


settings = Settings()
