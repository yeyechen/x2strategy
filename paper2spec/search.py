"""Academic paper search — arXiv + SSRN + Google Scholar.

Provides a unified search interface for quantitative finance papers.
Results include title, authors, abstract, URL, and source.
"""

import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import time

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
SSRN_SEARCH = "https://papers.ssrn.com/sol3/results.cfm"


@dataclass
class SearchResult:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    url: str = ""
    source: str = ""  # arxiv | ssrn | scholar
    published: str = ""
    pdf_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def search(query: str, *, max_results: int = 10, sources: Optional[list[str]] = None) -> list[SearchResult]:
    """Search for papers across configured sources.

    Args:
        query: Search query string.
        max_results: Max results per source.
        sources: Which sources to query. Default: ["arxiv"].
                 Options: "arxiv", "ssrn" (scraping, best-effort).

    Returns:
        Combined list of SearchResult.
    """
    if sources is None:
        sources = ["arxiv"]

    results: list[SearchResult] = []
    for src in sources:
        if src == "arxiv":
            results.extend(_search_arxiv(query, max_results=max_results))
        elif src == "ssrn":
            logger.warning("SSRN search is best-effort (HTML scraping); may break.")
            results.extend(_search_ssrn(query, max_results=max_results))
        else:
            logger.warning("Unknown source: %s (skipped)", src)

    return results


# ── arXiv ────────────────────────────────────────────────────


def _search_arxiv(query: str, *, max_results: int = 10) -> list[SearchResult]:
    """Search arXiv using their Atom API."""
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"
    logger.info("arXiv query: %s", url)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "paper2spec/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except Exception as e:
        logger.error("arXiv request failed: %s", e)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)
    results = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
        abstract = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")
        published = entry.findtext("atom:published", "", ns) or ""
        authors = [
            a.findtext("atom:name", "", ns)
            for a in entry.findall("atom:author", ns)
        ]

        # Links
        entry_url = ""
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            rel = link.get("rel", "")
            href = link.get("href", "")
            if rel == "alternate":
                entry_url = href
            elif link.get("title") == "pdf":
                pdf_url = href

        results.append(SearchResult(
            title=title,
            authors=authors,
            abstract=abstract[:500],
            url=entry_url,
            source="arxiv",
            published=published[:10],
            pdf_url=pdf_url,
        ))

    logger.info("arXiv returned %d results", len(results))
    return results


# ── SSRN (best-effort HTML scraping) ─────────────────────────


def _search_ssrn(query: str, *, max_results: int = 10) -> list[SearchResult]:
    """Best-effort search of SSRN via HTML scraping. May break if SSRN changes layout."""
    params = urllib.parse.urlencode({"txtKey_Words": query, "npage": 1})
    url = f"{SSRN_SEARCH}?{params}"
    logger.info("SSRN query: %s", url)

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; paper2spec/0.1)"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.error("SSRN request failed: %s", e)
        return []

    # Very basic extraction — SSRN HTML is complex, this is best-effort
    results = []
    # Look for title links: <a class="title" href="...">Title</a>
    for m in re.finditer(
        r'href="(https://papers\.ssrn\.com/sol3/papers\.cfm\?abstract_id=\d+)"[^>]*>\s*<[^>]*font[^>]*>([^<]+)',
        html,
    ):
        if len(results) >= max_results:
            break
        results.append(SearchResult(
            title=m.group(2).strip(),
            url=m.group(1),
            source="ssrn",
        ))

    logger.info("SSRN returned %d results", len(results))
    return results
