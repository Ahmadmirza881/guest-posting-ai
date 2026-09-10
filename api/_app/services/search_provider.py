"""Search Engine Discovery Provider Module for Step 10.

Implements multi-query generation and search provider integrations (SerpAPI, Google Custom Search,
Brave Search, ValueSerp) to discover candidate website URLs.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel
from app.config import settings
from app.utils.cache import app_cache, generate_cache_key
from app.utils.rate_limiter import get_http_limiter
from app.utils.retry import execute_with_retry

logger = logging.getLogger(__name__)

# Standard guest-posting query patterns
GUEST_POST_QUERY_PATTERNS: list[str] = [
    "{keyword} write for us",
    "{keyword} guest post",
    "{keyword} submit article",
    "{keyword} become a contributor",
    "{keyword} guest author",
]


def generate_guest_post_queries(keyword: str) -> list[str]:
    """Generate guest-post search queries for a given niche/keyword.

    Args:
        keyword: Niche or topic entered by the user (e.g. "AI", "Digital Marketing").

    Returns:
        List of formatted search query strings.
    """
    cleaned = keyword.strip()
    if not cleaned:
        return []
    return [pattern.format(keyword=cleaned) for pattern in GUEST_POST_QUERY_PATTERNS]


def extract_domain_from_url(url: str) -> str:
    """Extract host/domain from a URL for basic record creation."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return url.lower()


class CandidateSearchResult(BaseModel):
    """Structured candidate website discovery result from a search engine."""
    title: str
    url: str
    snippet: str
    query_used: str
    domain: Optional[str] = None
    position: Optional[int] = None


class SearchProviderError(Exception):
    """Base exception for search provider errors."""
    pass


class SearchProviderConfigError(SearchProviderError):
    """Raised when search provider configuration or API key is missing."""
    pass


class SearchProviderRequestError(SearchProviderError):
    """Raised when an API request to the search provider fails."""
    pass


class BaseSearchProvider(ABC):
    """Abstract base class for search engine providers."""

    def __init__(self, api_key: str, timeout: float = 15.0):
        if not api_key:
            raise SearchProviderConfigError("SEARCH_API_KEY is required but not configured.")
        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int = 10,
        client: Optional[httpx.AsyncClient] = None
    ) -> list[CandidateSearchResult]:
        """Execute a search query and return structured candidate results."""
        pass


class SerpApiProvider(BaseSearchProvider):
    """Search provider implementation using SerpAPI (Google Search API)."""

    ENDPOINT = "https://serpapi.com/search.json"

    async def search(
        self,
        query: str,
        num_results: int = 10,
        client: Optional[httpx.AsyncClient] = None
    ) -> list[CandidateSearchResult]:
        params = {
            "engine": "google",
            "q": query,
            "num": min(max(num_results, 1), 100),
            "api_key": self.api_key,
        }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        async def _do_search():
            resp = await client.get(self.ENDPOINT, params=params)
            if resp.status_code == 429:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get("error", err_text)
                except Exception:
                    pass
                if any(x in err_text.lower() for x in ["verified email", "invalid api key", "unauthorized", "account"]):
                    raise SearchProviderConfigError(f"SerpAPI configuration error: {err_text}")
                raise SearchProviderRequestError(f"SerpAPI transient error {resp.status_code}: {err_text}")
            elif resp.status_code in (500, 502, 503, 504):
                raise SearchProviderRequestError(f"SerpAPI transient error {resp.status_code}: {resp.text}")
            return resp

        try:
            response = await execute_with_retry(
                _do_search,
                limiter=get_http_limiter(),
                operation_name=f"SerpAPI Search '{query}'",
            )
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", response.text)
                except Exception:
                    pass
                raise SearchProviderRequestError(
                    f"SerpAPI returned HTTP {response.status_code}: {error_detail}"
                )

            data = response.json()
            organic_results = data.get("organic_results", [])
            candidates: list[CandidateSearchResult] = []

            for item in organic_results:
                url = item.get("link")
                if not url:
                    continue
                candidates.append(
                    CandidateSearchResult(
                        title=item.get("title", ""),
                        url=url,
                        snippet=item.get("snippet", ""),
                        query_used=query,
                        domain=extract_domain_from_url(url),
                        position=item.get("position"),
                    )
                )

            return candidates

        except httpx.RequestError as e:
            raise SearchProviderRequestError(f"SerpAPI network error: {str(e)}") from e
        finally:
            if should_close:
                await client.aclose()


class GoogleCustomSearchProvider(BaseSearchProvider):
    """Search provider implementation using Google Custom Search JSON API."""

    ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, engine_id: Optional[str] = None, timeout: float = 15.0):
        super().__init__(api_key=api_key, timeout=timeout)
        if not engine_id:
            raise SearchProviderConfigError(
                "SEARCH_ENGINE_ID (cx) is required for Google Custom Search."
            )
        self.engine_id = engine_id

    async def search(
        self,
        query: str,
        num_results: int = 10,
        client: Optional[httpx.AsyncClient] = None
    ) -> list[CandidateSearchResult]:
        params = {
            "key": self.api_key,
            "cx": self.engine_id,
            "q": query,
            "num": min(max(num_results, 1), 10),
        }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        async def _do_search():
            resp = await client.get(self.ENDPOINT, params=params)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise SearchProviderRequestError(f"Google CSE transient error {resp.status_code}: {resp.text}")
            return resp

        try:
            response = await execute_with_retry(
                _do_search,
                limiter=get_http_limiter(),
                operation_name=f"Google CSE Search '{query}'",
            )
            if response.status_code != 200:
                raise SearchProviderRequestError(
                    f"Google Custom Search returned HTTP {response.status_code}: {response.text}"
                )

            data = response.json()
            items = data.get("items", [])
            candidates: list[CandidateSearchResult] = []

            for idx, item in enumerate(items, start=1):
                url = item.get("link")
                if not url:
                    continue
                candidates.append(
                    CandidateSearchResult(
                        title=item.get("title", ""),
                        url=url,
                        snippet=item.get("snippet", ""),
                        query_used=query,
                        domain=extract_domain_from_url(url),
                        position=idx,
                    )
                )

            return candidates

        except httpx.RequestError as e:
            raise SearchProviderRequestError(f"Google Custom Search network error: {str(e)}") from e
        finally:
            if should_close:
                await client.aclose()


class BraveSearchProvider(BaseSearchProvider):
    """Search provider implementation using Brave Search API."""

    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    async def search(
        self,
        query: str,
        num_results: int = 10,
        client: Optional[httpx.AsyncClient] = None
    ) -> list[CandidateSearchResult]:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": min(max(num_results, 1), 20),
        }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        async def _do_search():
            resp = await client.get(self.ENDPOINT, headers=headers, params=params)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise SearchProviderRequestError(f"Brave Search transient error {resp.status_code}: {resp.text}")
            return resp

        try:
            response = await execute_with_retry(
                _do_search,
                limiter=get_http_limiter(),
                operation_name=f"Brave Search '{query}'",
            )
            if response.status_code != 200:
                raise SearchProviderRequestError(
                    f"Brave Search returned HTTP {response.status_code}: {response.text}"
                )

            data = response.json()
            web_results = data.get("web", {}).get("results", [])
            candidates: list[CandidateSearchResult] = []

            for idx, item in enumerate(web_results, start=1):
                url = item.get("url")
                if not url:
                    continue
                candidates.append(
                    CandidateSearchResult(
                        title=item.get("title", ""),
                        url=url,
                        snippet=item.get("description", ""),
                        query_used=query,
                        domain=extract_domain_from_url(url),
                        position=idx,
                    )
                )

            return candidates

        except httpx.RequestError as e:
            raise SearchProviderRequestError(f"Brave Search network error: {str(e)}") from e
        finally:
            if should_close:
                await client.aclose()


class ValueSerpProvider(BaseSearchProvider):
    """Search provider implementation using ValueSerp API."""

    ENDPOINT = "https://api.valueserp.com/search"

    async def search(
        self,
        query: str,
        num_results: int = 10,
        client: Optional[httpx.AsyncClient] = None
    ) -> list[CandidateSearchResult]:
        params = {
            "api_key": self.api_key,
            "q": query,
            "num": min(max(num_results, 1), 100),
        }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        async def _do_search():
            resp = await client.get(self.ENDPOINT, params=params)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise SearchProviderRequestError(f"ValueSerp transient error {resp.status_code}: {resp.text}")
            return resp

        try:
            response = await execute_with_retry(
                _do_search,
                limiter=get_http_limiter(),
                operation_name=f"ValueSerp Search '{query}'",
            )
            if response.status_code != 200:
                raise SearchProviderRequestError(
                    f"ValueSerp returned HTTP {response.status_code}: {response.text}"
                )

            data = response.json()
            organic_results = data.get("organic_results", [])
            candidates: list[CandidateSearchResult] = []

            for item in organic_results:
                url = item.get("link")
                if not url:
                    continue
                candidates.append(
                    CandidateSearchResult(
                        title=item.get("title", ""),
                        url=url,
                        snippet=item.get("snippet", ""),
                        query_used=query,
                        domain=extract_domain_from_url(url),
                        position=item.get("position"),
                    )
                )

            return candidates

        except httpx.RequestError as e:
            raise SearchProviderRequestError(f"ValueSerp network error: {str(e)}") from e
        finally:
            if should_close:
                await client.aclose()


class TavilySearchProvider(BaseSearchProvider):
    """Search provider implementation using Tavily Search API (AI-native web search)."""

    ENDPOINT = "https://api.tavily.com/search"

    async def search(
        self,
        query: str,
        num_results: int = 10,
        client: Optional[httpx.AsyncClient] = None
    ) -> list[CandidateSearchResult]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": min(max(num_results, 1), 20),
        }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        async def _do_search():
            resp = await client.post(
                self.ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code in (401, 403):
                err_text = resp.text
                try:
                    err_text = resp.json().get("detail", err_text)
                except Exception:
                    pass
                raise SearchProviderConfigError(f"Tavily authentication error ({resp.status_code}): {err_text}")
            elif resp.status_code == 429:
                err_text = resp.text
                try:
                    err_text = resp.json().get("detail", err_text)
                except Exception:
                    pass
                raise SearchProviderRequestError(f"Tavily rate limited (429): {err_text}")
            elif resp.status_code in (500, 502, 503, 504):
                raise SearchProviderRequestError(f"Tavily server error ({resp.status_code}): {resp.text}")
            return resp

        try:
            response = await execute_with_retry(
                _do_search,
                limiter=get_http_limiter(),
                operation_name=f"Tavily Search '{query}'",
            )
            if response.status_code != 200:
                raise SearchProviderRequestError(
                    f"Tavily returned HTTP {response.status_code}: {response.text}"
                )

            data = response.json()
            results = data.get("results", [])
            candidates: list[CandidateSearchResult] = []

            for idx, item in enumerate(results, start=1):
                url = item.get("url")
                if not url:
                    continue
                candidates.append(
                    CandidateSearchResult(
                        title=item.get("title", ""),
                        url=url,
                        snippet=item.get("content", ""),
                        query_used=query,
                        domain=extract_domain_from_url(url),
                        position=idx,
                    )
                )

            return candidates

        except httpx.RequestError as e:
            raise SearchProviderRequestError(f"Tavily network error: {str(e)}") from e
        finally:
            if should_close:
                await client.aclose()


class DuckDuckGoSearchProvider(BaseSearchProvider):
    """Search provider implementation using DuckDuckGo HTML search (No API key required)."""

    ENDPOINT = "https://html.duckduckgo.com/html/"

    def __init__(self, api_key: str = "none", timeout: float = 15.0):
        super().__init__(api_key=api_key or "none", timeout=timeout)

    async def search(
        self,
        query: str,
        num_results: int = 10,
        client: Optional[httpx.AsyncClient] = None
    ) -> list[CandidateSearchResult]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        }
        data = {"q": query}

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
            should_close = True

        async def _do_search():
            resp = await client.post(self.ENDPOINT, data=data, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise SearchProviderRequestError(f"DuckDuckGo transient error {resp.status_code}")
            return resp

        try:
            response = await execute_with_retry(
                _do_search,
                limiter=get_http_limiter(),
                operation_name=f"DuckDuckGo Search '{query}'",
            )
            if response.status_code != 200:
                raise SearchProviderRequestError(
                    f"DuckDuckGo returned HTTP {response.status_code}"
                )

            soup = BeautifulSoup(response.text, "html.parser")
            candidates: list[CandidateSearchResult] = []

            for idx, el in enumerate(soup.select(".result__body"), start=1):
                link = el.select_one(".result__title a")
                snippet_el = el.select_one(".result__snippet")
                if link and link.get("href"):
                    href = link["href"]
                    if "/uddg=" in href:
                        parsed = urlparse(href)
                        qs = parse_qs(parsed.query)
                        href = qs.get("uddg", [href])[0]

                    if not href.startswith(("http://", "https://")):
                        continue

                    title = link.get_text(strip=True)
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                    candidates.append(
                        CandidateSearchResult(
                            title=title,
                            url=href,
                            snippet=snippet,
                            query_used=query,
                            domain=extract_domain_from_url(href),
                            position=idx,
                        )
                    )
                    if len(candidates) >= num_results:
                        break

            return candidates

        except httpx.RequestError as e:
            raise SearchProviderRequestError(f"DuckDuckGo network error: {str(e)}") from e
        finally:
            if should_close:
                await client.aclose()


def get_search_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    engine_id: Optional[str] = None,
    timeout: Optional[float] = None
) -> BaseSearchProvider:
    """Factory function returning the configured search provider instance.

    Args:
        provider_name: Name of search provider (tavily, duckduckgo, serpapi, google_custom_search, brave, valueserp).
        api_key: API key. If omitted, reads from settings.
        engine_id: Search engine ID (for Google CSE).
        timeout: Timeout in seconds.

    Returns:
        Instantiated BaseSearchProvider.

    Raises:
        SearchProviderConfigError: If provider or API key is unconfigured or unknown.
    """
    name = (provider_name if provider_name is not None else settings.SEARCH_PROVIDER).lower().strip()
    timeout_sec = timeout if timeout is not None else settings.SEARCH_TIMEOUT_SECONDS

    # 1. Tavily AI Search
    if name == "tavily":
        tavily_key = api_key if api_key is not None else (settings.TAVILY_API_KEY or settings.SEARCH_API_KEY)
        if not tavily_key:
            raise SearchProviderConfigError(
                "TAVILY_API_KEY is not configured in backend environment variables."
            )
        return TavilySearchProvider(api_key=tavily_key, timeout=timeout_sec)

    # 2. DuckDuckGo (zero API key fallback)
    if name in ("duckduckgo", "ddg"):
        return DuckDuckGoSearchProvider(api_key="none", timeout=timeout_sec)

    # Key resolution for traditional providers
    key = api_key if api_key is not None else settings.SEARCH_API_KEY
    if not key:
        raise SearchProviderConfigError(
            "SEARCH_API_KEY is not configured in backend environment variables."
        )

    if engine_id is not None:
        cx = engine_id
    elif provider_name is None or name in ("google_custom_search", "google_cse", "google"):
        cx = settings.SEARCH_ENGINE_ID if settings.SEARCH_PROVIDER in ("google_custom_search", "google_cse", "google") else None
    else:
        cx = None

    if name in ("serpapi", "serp_api"):
        return SerpApiProvider(api_key=key, timeout=timeout_sec)
    elif name in ("google_custom_search", "google_cse", "google"):
        return GoogleCustomSearchProvider(api_key=key, engine_id=cx, timeout=timeout_sec)
    elif name == "brave":
        return BraveSearchProvider(api_key=key, timeout=timeout_sec)
    elif name in ("valueserp", "value_serp"):
        return ValueSerpProvider(api_key=key, timeout=timeout_sec)
    else:
        raise SearchProviderConfigError(
            f"Unsupported search provider '{name}'. Supported: tavily, duckduckgo, serpapi, google_custom_search, brave, valueserp"
        )


async def discover_candidates_for_keyword(
    keyword: str,
    target_count: int = 100,
    provider: Optional[BaseSearchProvider] = None,
    client: Optional[httpx.AsyncClient] = None
) -> list[CandidateSearchResult]:
    """Execute multiple search queries for keyword to discover candidate website URLs.

    Enforces:
    - In-memory TTL caching (Step 24).
    - Rate-limited and retried search provider requests (Step 24).

    Args:
        keyword: Search topic or niche (e.g., "AI", "Technology").
        target_count: Total requested target number of websites.
        provider: Optional search provider instance.
        client: Optional shared httpx.AsyncClient.

    Returns:
        List of CandidateSearchResult objects discovered across all query patterns.
    """
    if provider is None:
        provider = get_search_provider()

    queries = generate_guest_post_queries(keyword)
    if not queries:
        return []

    # Cache Lookup (Step 24)
    provider_name = provider.__class__.__name__
    cache_key = generate_cache_key("search_candidates", keyword.strip().lower(), target_count, provider_name)
    cached_candidates = await app_cache.get(cache_key)
    if cached_candidates is not None and isinstance(cached_candidates, list):
        logger.debug(f"Cache hit for search discovery: {keyword}")
        return cached_candidates

    # Distribute requested count across the query patterns
    per_query_target = max(5, target_count // len(queries) + 1)

    all_candidates: list[CandidateSearchResult] = []
    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=provider.timeout)
        should_close = True

    try:
        for query in queries:
            try:
                results = await provider.search(
                    query=query,
                    num_results=per_query_target,
                    client=client
                )
                all_candidates.extend(results)
                # Stop early if total target count has been reached
                if len(all_candidates) >= target_count:
                    break
            except SearchProviderConfigError as err:
                logger.error(f"Search provider fatal configuration/account error: {err}. Halting remaining discovery queries.")
                break
            except SearchProviderError as err:
                logger.warning(f"Query '{query}' failed with search provider: {err}")
                continue

        final_candidates = all_candidates[:target_count] if target_count > 0 else all_candidates
        if final_candidates:
            await app_cache.set(cache_key, final_candidates)

        return final_candidates
    finally:
        if should_close:
            await client.aclose()
