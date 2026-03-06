import os
import pytest

# Set mock environment variables BEFORE any application code is imported.
# This prevents Pydantic validation errors when module-level tools 
# (like TavilySearch or ChatOpenAI) are instantiated during pytest collection.
os.environ["OPENAI_API_KEY"] = "mock-openai-key-for-testing"
os.environ["TAVILY_API_KEY"] = "mock-tavily-key-for-testing"
os.environ["USER_AGENT"] = "test-agent"
