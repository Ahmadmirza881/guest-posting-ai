"""Comprehensive Test Suite for Step 10: Search Engine Integration."""

import asyncio
from unittest.mock import AsyncMock, patch
import httpx

from app.database import init_db, SessionLocal
from app.models import Search, SearchResult, Website
from app.schemas.search import SearchCreate
from app.services.search_provider import (
    GUEST_POST_QUERY_PATTERNS,
    generate_guest_post_queries,
    extract_domain_from_url,
    CandidateSearchResult,
    SerpApiProvider,
    GoogleCustomSearchProvider,
    BraveSearchProvider,
    ValueSerpProvider,
    get_search_provider,
    discover_candidates_for_keyword,
    SearchProviderConfigError,
    SearchProviderRequestError,
)
from app.services.search_service import (
    create_search,
    execute_search_discovery,
    get_search_by_id,
)
from app.main import app


def test_query_generation():
    """Test guest-posting search query pattern generation."""
    print("Running Test: Query Generation...")
    
    # Test single word keyword
    queries_ai = generate_guest_post_queries("AI")
    assert len(queries_ai) == 5
    assert queries_ai == [
        "AI write for us",
        "AI guest post",
        "AI submit article",
        "AI become a contributor",
        "AI guest author",
    ]
    
    # Test multi-word keyword with whitespace
    queries_dm = generate_guest_post_queries("  Digital Marketing  ")
    assert len(queries_dm) == 5
    assert queries_dm[0] == "Digital Marketing write for us"
    assert queries_dm[1] == "Digital Marketing guest post"
    assert queries_dm[2] == "Digital Marketing submit article"
    assert queries_dm[3] == "Digital Marketing become a contributor"
    assert queries_dm[4] == "Digital Marketing guest author"

    # Test empty keyword
    assert generate_guest_post_queries("") == []
    assert generate_guest_post_queries("   ") == []

    print("  [PASS] Query generation produces expected query patterns.")


def test_domain_extraction():
    """Test URL domain extraction helper."""
    print("Running Test: Domain Extraction...")
    assert extract_domain_from_url("https://www.example.com/write-for-us") == "example.com"
    assert extract_domain_from_url("http://techblog.org/guest-post?id=123") == "techblog.org"
    assert extract_domain_from_url("https://sub.domain.co.uk/articles") == "sub.domain.co.uk"
    print("  [PASS] Domain extraction handles URLs cleanly.")


def test_provider_factory_and_config():
    """Test search provider factory and configuration validation."""
    print("Running Test: Provider Factory & Configuration Validation...")

    # Missing API key
    try:
        get_search_provider(provider_name="serpapi", api_key="")
        assert False, "Expected SearchProviderConfigError for missing API key"
    except SearchProviderConfigError:
        pass

    # Unsupported provider
    try:
        get_search_provider(provider_name="unknown_provider", api_key="dummy_key")
        assert False, "Expected SearchProviderConfigError for unsupported provider"
    except SearchProviderConfigError:
        pass

    # Google CSE missing engine ID
    try:
        get_search_provider(provider_name="google_custom_search", api_key="dummy_key", engine_id=None)
        assert False, "Expected SearchProviderConfigError for Google CSE missing engine_id"
    except SearchProviderConfigError:
        pass

    # Valid providers
    serp = get_search_provider(provider_name="serpapi", api_key="key123")
    assert isinstance(serp, SerpApiProvider)

    google = get_search_provider(provider_name="google_custom_search", api_key="key123", engine_id="cx456")
    assert isinstance(google, GoogleCustomSearchProvider)

    brave = get_search_provider(provider_name="brave", api_key="key123")
    assert isinstance(brave, BraveSearchProvider)

    val = get_search_provider(provider_name="valueserp", api_key="key123")
    assert isinstance(val, ValueSerpProvider)

    print("  [PASS] Provider factory correctly instantiates and validates providers.")


async def test_serpapi_provider_mocked():
    """Test SerpAPI search provider with mocked HTTP response."""
    print("Running Test: SerpApiProvider (Mocked HTTP)...")

    provider = SerpApiProvider(api_key="mock_serp_key")
    mock_response_data = {
        "organic_results": [
            {
                "title": "Tech Blog - Write for Us",
                "link": "https://techblog.com/write-for-us",
                "snippet": "We accept guest submissions on AI and Tech.",
                "position": 1
            },
            {
                "title": "AI Insights Contributor Guidelines",
                "link": "https://aiinsights.io/guest-post",
                "snippet": "Submit your guest article to our editorial team.",
                "position": 2
            }
        ]
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.get.return_value = mock_resp

    results = await provider.search("AI write for us", num_results=10, client=mock_client)
    assert len(results) == 2
    assert results[0].title == "Tech Blog - Write for Us"
    assert results[0].url == "https://techblog.com/write-for-us"
    assert results[0].domain == "techblog.com"
    assert results[0].position == 1
    assert results[0].query_used == "AI write for us"
    assert results[1].domain == "aiinsights.io"

    print("  [PASS] SerpApiProvider parses organic results into CandidateSearchResult.")


async def test_google_cse_provider_mocked():
    """Test Google Custom Search provider with mocked HTTP response."""
    print("Running Test: GoogleCustomSearchProvider (Mocked HTTP)...")

    provider = GoogleCustomSearchProvider(api_key="mock_key", engine_id="mock_cx")
    mock_response_data = {
        "items": [
            {
                "title": "Submit an Article - DevCorner",
                "link": "https://devcorner.com/submit-article",
                "snippet": "Read our guest author guidelines."
            }
        ]
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.get.return_value = mock_resp

    results = await provider.search("AI submit article", num_results=5, client=mock_client)
    assert len(results) == 1
    assert results[0].title == "Submit an Article - DevCorner"
    assert results[0].url == "https://devcorner.com/submit-article"
    assert results[0].domain == "devcorner.com"

    print("  [PASS] GoogleCustomSearchProvider parses items into CandidateSearchResult.")


async def test_brave_search_provider_mocked():
    """Test Brave Search provider with mocked HTTP response."""
    print("Running Test: BraveSearchProvider (Mocked HTTP)...")

    provider = BraveSearchProvider(api_key="mock_brave_key")
    mock_response_data = {
        "web": {
            "results": [
                {
                    "title": "Become a Contributor - DataMag",
                    "url": "https://datamag.org/contribute",
                    "description": "Guidelines for guest authors and contributors."
                }
            ]
        }
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data
    mock_client.get.return_value = mock_resp

    results = await provider.search("AI become a contributor", num_results=5, client=mock_client)
    assert len(results) == 1
    assert results[0].title == "Become a Contributor - DataMag"
    assert results[0].url == "https://datamag.org/contribute"
    assert results[0].domain == "datamag.org"

    print("  [PASS] BraveSearchProvider parses web.results into CandidateSearchResult.")


async def test_provider_error_handling():
    """Test error handling on HTTP error codes and network failures."""
    print("Running Test: Search Provider Error Handling...")

    provider = SerpApiProvider(api_key="mock_key")
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # 1. HTTP 401 Unauthorized / Invalid API Key
    mock_resp_401 = AsyncMock(spec=httpx.Response)
    mock_resp_401.status_code = 401
    mock_resp_401.text = "Invalid API key"
    mock_resp_401.json.return_value = {"error": "Invalid API key"}
    mock_client.get.return_value = mock_resp_401

    try:
        await provider.search("AI write for us", client=mock_client)
        assert False, "Expected SearchProviderRequestError on 401"
    except SearchProviderRequestError as e:
        assert "401" in str(e) or "Invalid API key" in str(e)

    # 2. Network Timeout / Connection Error
    mock_client.get.side_effect = httpx.ConnectTimeout("Connection timed out")
    try:
        await provider.search("AI write for us", client=mock_client)
        assert False, "Expected SearchProviderRequestError on ConnectTimeout"
    except SearchProviderRequestError as e:
        assert "network error" in str(e).lower() or "timeout" in str(e).lower()

    print("  [PASS] Search provider raises structured SearchProviderRequestError on API and network errors.")


async def test_multi_query_candidate_discovery():
    """Test multi-query discovery orchestration across all query patterns."""
    print("Running Test: Multi-Query Candidate Discovery Orchestration...")

    class MockProvider(SerpApiProvider):
        def __init__(self):
            super().__init__(api_key="mock_key")
            self.queried_list = []

        async def search(self, query: str, num_results: int = 10, client=None):
            self.queried_list.append(query)
            clean_q = query.replace(" ", "_").lower()
            return [
                CandidateSearchResult(
                    title=f"Result for {query}",
                    url=f"https://{clean_q}.example.com/page",
                    snippet=f"Snippet for {query}",
                    query_used=query,
                    domain=f"{clean_q}.example.com",
                    position=1
                )
            ]

    mock_prov = MockProvider()
    candidates = await discover_candidates_for_keyword(
        keyword="Machine Learning",
        target_count=20,
        provider=mock_prov
    )

    # Verify all 5 query patterns were executed
    assert len(mock_prov.queried_list) == 5
    assert len(candidates) == 5
    assert candidates[0].query_used == "Machine Learning write for us"
    assert candidates[1].query_used == "Machine Learning guest post"
    assert candidates[2].query_used == "Machine Learning submit article"
    assert candidates[3].query_used == "Machine Learning become a contributor"
    assert candidates[4].query_used == "Machine Learning guest author"

    print("  [PASS] Multi-query discovery queried all 5 patterns and aggregated candidate URLs.")


async def test_database_persistence_and_search_integration():
    """Test database persistence of discovered candidates and association with Search entity."""
    print("Running Test: Database Persistence and Search Integration...")
    init_db()

    db = SessionLocal()
    try:
        # Create a search
        search_in = SearchCreate(keyword="Cloud Computing", requested_website_count=10)
        search = create_search(db=db, search_in=search_in)
        assert search.id is not None
        assert search.status == "pending"

        # Mock provider that returns 3 candidate websites
        class MockDiscoveryProvider(SerpApiProvider):
            def __init__(self):
                super().__init__(api_key="mock_key")

            async def search(self, query: str, num_results: int = 10, client=None):
                if "write for us" in query:
                    return [
                        CandidateSearchResult(
                            title="Cloud Journal - Write for Us",
                            url="https://cloudjournal.com/write-for-us",
                            snippet="Write for our cloud tech community.",
                            query_used=query,
                            domain="cloudjournal.com",
                            position=1
                        ),
                        CandidateSearchResult(
                            title="DevOps Cloud Hub",
                            url="https://devopscloud.io/contribute",
                            snippet="Submit guest post articles.",
                            query_used=query,
                            domain="devopscloud.io",
                            position=2
                        )
                    ]
                return []

        # Execute discovery
        updated_search = await execute_search_discovery(
            db=db,
            search=search,
            provider=MockDiscoveryProvider()
        )

        assert updated_search.status == "discovered"
        
        # Verify in DB
        fetched_search = get_search_by_id(db=db, search_id=search.id)
        assert fetched_search is not None
        assert len(fetched_search.results) == 2
        
        domains = [r.website.domain for r in fetched_search.results]
        assert "cloudjournal.com" in domains
        assert "devopscloud.io" in domains

        for r in fetched_search.results:
            assert r.status == "discovered"
            assert r.search_id == search.id
            assert r.website_id is not None
            assert r.website.url is not None

        print(f"  [PASS] Discovery populated {len(fetched_search.results)} candidate websites associated with Search ID #{search.id}.")
    finally:
        db.close()


async def test_api_endpoint_integration():
    """Test full FastAPI endpoint integration with search creation and discovery."""
    print("Running Test: FastAPI Endpoints Integration (/api/searches)...")
    init_db()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a search
        res = await client.post(
            "/api/searches",
            json={"keyword": "Cybersecurity", "requested_website_count": 25}
        )
        assert res.status_code == 201
        data = res.json()
        search_id = data["id"]
        assert data["keyword"] == "Cybersecurity"
        assert data["requested_website_count"] == 25
        assert data["status"] in ("pending", "discovered", "no_results")

        # Get search details
        get_res = await client.get(f"/api/searches/{search_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["id"] == search_id
        assert get_data["keyword"] == "Cybersecurity"
        assert isinstance(get_data["results"], list)

        print("  [PASS] FastAPI /api/searches endpoint seamlessly integrates with discovery layer.")


async def main():
    print("=" * 60)
    print("STEP 10: SEARCH ENGINE INTEGRATION TEST SUITE")
    print("=" * 60)

    test_query_generation()
    test_domain_extraction()
    test_provider_factory_and_config()
    await test_serpapi_provider_mocked()
    await test_google_cse_provider_mocked()
    await test_brave_search_provider_mocked()
    await test_provider_error_handling()
    await test_multi_query_candidate_discovery()
    await test_database_persistence_and_search_integration()
    await test_api_endpoint_integration()

    print("=" * 60)
    print("ALL STEP 10 TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
