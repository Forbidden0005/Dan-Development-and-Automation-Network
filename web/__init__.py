"""Web tools: fetch pages and search the web."""

import json
import logging
import re
from html.parser import HTMLParser

import tool_registry as registry

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    """Simple HTML to text converter."""
    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._skip = False
        self._skip_tags = {"script", "style", "nav", "footer", "header"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self._text.append(text)

    def get_text(self) -> str:
        return "\n".join(self._text)


def _extract_text(html: str, max_chars: int = 15000) -> str:
    """Extract readable text from HTML."""
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass
    text = extractor.get_text()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text


def web_fetch(url: str, max_chars: int = 15000) -> str:
    """Fetch a web page and extract text."""
    try:
        import httpx
    except ImportError:
        return "Error: pip install httpx"

    try:
        headers = {"User-Agent": "Dan/2.0 (Development Automation Network)"}
        with httpx.Client(follow_redirects=True, timeout=15) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()

        content_type = r.headers.get("content-type", "")
        if "json" in content_type:
            return json.dumps(r.json(), indent=2)[:max_chars]
        elif "text" in content_type or "html" in content_type:
            return _extract_text(r.text, max_chars)
        else:
            return f"Binary content ({content_type}), {len(r.content)} bytes"
    except Exception as e:
        return f"Error fetching {url}: {e}"


def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo (no API key required)."""
    try:
        from ddgs import DDGS
    except ImportError:
        return "Error: pip install ddgs"

    try:
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=num_results)):
                title   = r.get("title", "").strip()
                url     = r.get("href", "").strip()
                snippet = r.get("body", "").strip()
                results.append(f"{i+1}. {title}\n   {url}\n   {snippet}")

        if not results:
            return f"No results found for: {query}"
        return "\n\n".join(results)
    except Exception as e:
        return f"Error searching for '{query}': {e}"


def register_web_tools() -> None:
    """Register web tools."""
    registry.register(
        name="WebFetch", description="Fetch a web page and extract text content.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_chars": {"type": "integer", "description": "Max chars to return", "default": 15000},
            },
            "required": ["url"],
        },
        handler=web_fetch, category="web",
    )

    registry.register(
        name="WebSearch", description="Search the web and return results.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results", "default": 5},
            },
            "required": ["query"],
        },
        handler=web_search, category="web",
    )
