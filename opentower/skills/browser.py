"""Browser skill — web browsing, content extraction, and search.

Uses httpx for lightweight fetching (no browser dependency required).
Optional Playwright integration for JS-heavy pages.

This is the #1 most-called Agent skill globally.
"""

from __future__ import annotations

import re
import logging

import httpx

from opentower.skills import skill

logger = logging.getLogger("opentower.skills.browser")

_TIMEOUT = 20
_MAX_CONTENT = 8000  # chars


def _html_to_text(html: str) -> str:
    """Quick-and-dirty HTML → plain text conversion."""
    # Remove scripts & styles
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Extract title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    # Strip tags
    text = re.sub(r"<[^>]+>", "\n", text)
    # Clean whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip(), title


@skill(
    "browse",
    description="Open a URL and extract the text content of the page",
    parameters='{"url": "string (required) — full URL to visit"}',
)
async def browse(url: str = "") -> dict:
    """Fetch a URL and return extracted text content."""
    if not url:
        return {"error": "No URL provided"}

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info("Browsing: %s", url[:80])

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; OpenTower/3.1; +https://github.com/EmpireTower/OpenTower)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5,zh-CN;q=0.3",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type:
            text, title = _html_to_text(resp.text)
        else:
            text = resp.text[:_MAX_CONTENT]
            title = ""

        return {
            "url": str(resp.url),
            "title": title,
            "status": resp.status_code,
            "content": text[:_MAX_CONTENT],
            "content_length": len(text),
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {str(e)[:200]}", "url": url}
    except httpx.ConnectError:
        return {"error": f"Connection failed: {url}"}
    except httpx.ReadTimeout:
        return {"error": f"Timeout after {_TIMEOUT}s: {url}"}
    except Exception as e:
        return {"error": str(e)[:300]}


@skill(
    "web_search",
    description="Search the web using DuckDuckGo and return summarized results",
    parameters='{"query": "string (required) — search query"}',
)
async def web_search(query: str = "") -> dict:
    """Search via DuckDuckGo HTML (no API key needed)."""
    if not query:
        return {"error": "No query provided"}

    logger.info("Searching: %s", query[:60])

    try:
        search_url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; OpenTower/3.1)",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.post(search_url, data={"q": query}, headers=headers)
            resp.raise_for_status()

        # Extract result links and snippets
        results = []
        # Match DuckDuckGo result blocks
        for match in re.finditer(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</(?:td|div)',
            resp.text, re.DOTALL
        ):
            href = match.group(1)
            title_raw = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            snippet_raw = re.sub(r"<[^>]+>", "", match.group(3)).strip()

            # DuckDuckGo wraps URLs in a redirect
            if "uddg=" in href:
                url_match = re.search(r"uddg=([^&]+)", href)
                if url_match:
                    from urllib.parse import unquote
                    href = unquote(url_match.group(1))

            results.append({
                "title": title_raw[:100],
                "url": href,
                "snippet": snippet_raw[:200],
            })
            if len(results) >= 8:
                break

        return {
            "query": query,
            "result_count": len(results),
            "results": results,
        }

    except Exception as e:
        return {"error": f"Search failed: {str(e)[:200]}"}
