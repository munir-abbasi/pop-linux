import pytest
from unittest.mock import AsyncMock, MagicMock
from pop_linux.providers import get_provider, OpenAlexProvider, SemanticScholarProvider, CrossRefProvider, PubMedProvider


def test_get_provider():
    p_alex = get_provider("openalex")
    assert isinstance(p_alex, OpenAlexProvider)

    p_s2 = get_provider("semanticscholar")
    assert isinstance(p_s2, SemanticScholarProvider)

    p_crossref = get_provider("crossref")
    assert isinstance(p_crossref, CrossRefProvider)

    p_pubmed = get_provider("pubmed")
    assert isinstance(p_pubmed, PubMedProvider)

    with pytest.raises(ValueError):
        get_provider("non_existent_provider")


@pytest.mark.asyncio
async def test_openalex_provider_mock(monkeypatch):
    provider = OpenAlexProvider()
    mock_json = {
        "meta": {"count": 1},
        "results": [
            {
                "id": "W12345",
                "display_name": "Test OpenAlex Paper",
                "publication_year": 2022,
                "cited_by_count": 15,
                "doi": "https://doi.org/10.1000/123",
                "primary_location": {
                    "landing_page_url": "https://example.com/p",
                    "source": {"display_name": "Test Journal"}
                },
                "authorships": [
                    {"author": {"display_name": "Dr. Smith", "id": "A1"}}
                ],
                "abstract_inverted_index": {"Hello": [0], "world": [1]}
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_json)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    res = await provider.search("test query", limit=10)
    assert res.provider == "openalex"
    assert res.total_found == 1
    assert len(res.papers) == 1
    assert res.papers[0].title == "Test OpenAlex Paper"
    assert res.papers[0].abstract == "Hello world"
    assert res.papers[0].citations == 15
    assert res.metrics.h_index == 1


@pytest.mark.asyncio
async def test_crossref_provider_mock(monkeypatch):
    provider = CrossRefProvider()
    mock_json = {
        "message": {
            "total-results": 1,
            "items": [
                {
                    "title": ["Test CrossRef Work"],
                    "is-referenced-by-count": 25,
                    "DOI": "10.1016/test",
                    "container-title": ["CrossRef Journal"],
                    "published-print": {"date-parts": [[2021]]},
                    "author": [{"given": "John", "family": "Doe"}],
                    "abstract": "<jats:p>Abstract with tags</jats:p>"
                }
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_json)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    res = await provider.search("crossref query")
    assert res.provider == "crossref"
    assert res.papers[0].title == "Test CrossRef Work"
    assert res.papers[0].abstract == "Abstract with tags"
    assert res.papers[0].citations == 25


def test_provider_filter_papers():
    from pop_linux.models import Paper
    provider = OpenAlexProvider()
    papers = [
        Paper(title="P1", year=2015, citations=2),
        Paper(title="P2", year=2020, citations=12),
        Paper(title="P3", year=2023, citations=50),
    ]

    filtered = provider.filter_papers(papers, year_from=2018, min_citations=10)
    assert len(filtered) == 2
    assert [p.title for p in filtered] == ["P2", "P3"]

    filtered_range = provider.filter_papers(papers, year_from=2018, year_to=2021)
    assert len(filtered_range) == 1
    assert filtered_range[0].title == "P2"
