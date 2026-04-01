import asyncio
import os

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

load_dotenv()
tavily_tool = TavilySearch(max_results=5, topic="general")

_DEFAULT_USER_AGENT = os.getenv("USER_AGENT", "orchagent-web-scraper/1.0")
_MAX_SCRAPE_URLS = 4
_MAX_HTML_CHARS = 400000


def _scrape_url(url: str) -> dict[str, str]:
    with requests.Session() as session:
        session.headers.update({"User-Agent": _DEFAULT_USER_AGENT})
        try:
            response = session.get(url, timeout=12)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "html" not in content_type:
                return {
                    "url": url,
                    "title": "",
                    "page_content": f"Skipped non-HTML content from {url} (content-type: {content_type or 'unknown'}).",
                }

            soup = BeautifulSoup(response.text[:_MAX_HTML_CHARS], "html.parser")
            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            page_content = soup.get_text(separator="\n", strip=True)[:_MAX_HTML_CHARS]
            return {
                "url": url,
                "title": title,
                "page_content": page_content,
            }
        except Exception as exc:
            return {
                "url": url,
                "title": "",
                "page_content": f"Error scraping {url}: {exc}",
            }


async def _scrape_urls(urls: list[str]) -> list[dict[str, str]]:
    bounded_urls = urls[:_MAX_SCRAPE_URLS]
    return await asyncio.gather(
        *(asyncio.to_thread(_scrape_url, url) for url in bounded_urls)
    )


@tool
async def scrape_webpages(urls: list[str]) -> str:
    """Use requests and bs4 to scrape the provided web pages for detailed information."""
    docs = await _scrape_urls(urls)
    return "\n\n".join(
        [
            f'<Document name="{doc.get("title", "")}" url="{doc.get("url", "")}">\n{doc.get("page_content", "")}\n</Document>'
            for doc in docs
        ]
    )
