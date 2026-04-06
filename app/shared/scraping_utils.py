"""Utilities for web scraping with anti-bot evasion techniques."""

import random
from typing import Any

# ── User-Agents rotatorios ─────────────────────────────────────
# Lista de User-Agents reales de navegadores actuales
# Se rotan para evitar detección por fingerprint estático

USER_AGENTS = [
    # Chrome (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    # Firefox (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Safari (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    # Edge (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]


# ── Headers completos para simular navegador real ────────────────

def get_random_headers() -> dict[str, str]:
    """Generate realistic browser headers with randomized User-Agent."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": random.choice([
            "en-US,en;q=0.9",
            "en-GB,en;q=0.9,en-US;q=0.8",
            "es-PE,es;q=0.9,en;q=0.8",
        ]),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


def get_headers_with_referer(referer: str) -> dict[str, str]:
    """Generate headers with a specific referer URL.

    Simulates navigation from a search results page.
    """
    headers = get_random_headers()
    headers["Referer"] = referer
    headers["Sec-Fetch-Site"] = "same-origin"
    return headers


# ── Retry configuration ──────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds
TIMEOUT = 30.0

# ── Domain-specific referers ───────────────────────────────────

DOMAIN_REFERERS = {
    "indeed.com": {
        "main": "https://www.indeed.com/",
        "search": "https://www.indeed.com/jobs?q=",
    },
    "bommerang.com": {
        "main": "https://www.bommerang.com/",
        "search": "https://www.bommerang.com/jobs/",
    },
}


def get_domain_referer(url: str) -> str:
    """Get an appropriate referer for the given URL.

    Args:
        url: The target URL.

    Returns:
        A referer URL from the same domain.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if not parsed.hostname:
        return "https://www.google.com/"

    hostname = parsed.hostname.lower()

    # Check if we have a referer for this domain
    for domain, referers in DOMAIN_REFERERS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return referers["main"]

    # Fallback to Google search (common real-world scenario)
    return f"https://www.google.com/search?q={parsed.path}"
