from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_community.document_loaders import WebBaseLoader
from langchain_tavily import TavilySearch

load_dotenv()
tavily_tool = TavilySearch(max_results=5, topic="general")


@tool
async def scrape_webpages(urls: list[str]) -> str:
    """Use requests and bs4 to scrape the provided web pages for detailed information."""
    loader = WebBaseLoader(urls)
    docs = loader.aload()
    return "\n\n".join(
        [
            f'<Document name="{doc.metadata.get("title", "")}">\n{doc.page_content}\n</Document>'
            for doc in docs
        ]
    )
