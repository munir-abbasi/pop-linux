from pop_linux.providers.google_scholar import (
    GoogleScholarProvider,
    parse_google_scholar_html,
    parse_google_scholar_profile_html,
)

SAMPLE_PROFILE_HTML = """
<html><body><table>
<tr class="gsc_a_tr">
  <td class="gsc_a_t">
    <a class="gsc_a_at" href="/citations?view_op=view_citation&amp;user=U1&amp;citation_for_view=ABC">Profile Paper One</a>
    <div class="gs_gray">A Smith, B Jones</div>
    <div class="gs_gray">Nature Medicine</div>
  </td>
  <td class="gsc_a_c"><a class="gsc_a_ac">142</a></td>
  <td class="gsc_a_y"><span>2023</span></td>
</tr>
<tr class="gsc_a_tr">
  <td class="gsc_a_t">
    <a class="gsc_a_at" href="https://example.org/full">Profile Paper Two</a>
    <div class="gs_gray">C Williams</div>
    <div class="gs_gray">AI Review</div>
  </td>
  <td class="gsc_a_c"><a class="gsc_a_ac">25</a></td>
  <td class="gsc_a_y"><span>2020</span></td>
</tr>
</table></body></html>
"""


SAMPLE_SCHOLAR_HTML = """
<html>
<body>
<div class="gs_r gs_or gs_scl">
  <div class="gs_ri">
    <h3 class="gs_rt"><a href="https://doi.org/10.1016/j.ai.2023.01">Deep Learning in Healthcare</a></h3>
    <div class="gs_a">A Smith, B Jones - Nature Medicine, 2023 - nature.com</div>
    <div class="gs_rs">We present a novel deep learning framework for clinical diagnostics...</div>
    <div class="gs_fl">
      <a href="/scholar?cites=12345">Cited by 142</a>
    </div>
  </div>
</div>
<div class="gs_r gs_or gs_scl">
  <div class="gs_ri">
    <h3 class="gs_rt"><a href="https://example.org/paper2">[PDF] Reinforcement Learning Overview</a></h3>
    <div class="gs_a">C Williams - AI Review, 2020 - Springer</div>
    <div class="gs_rs">A comprehensive survey of modern RL algorithms...</div>
    <div class="gs_fl">
      <a href="/scholar?cites=6789">Cited by 25</a>
    </div>
  </div>
</div>
</body>
</html>
"""


def test_parse_google_scholar_html():
    papers = parse_google_scholar_html(SAMPLE_SCHOLAR_HTML)
    assert len(papers) == 2

    p1 = papers[0]
    assert p1.title == "Deep Learning in Healthcare"
    assert p1.author_string == "A Smith, B Jones"
    assert p1.journal == "Nature Medicine"
    assert p1.year == 2023
    assert p1.citations == 142
    assert p1.doi == "10.1016/j.ai.2023.01"
    assert "novel deep learning framework" in p1.abstract

    p2 = papers[1]
    assert p2.title == "Reinforcement Learning Overview"
    assert p2.author_string == "C Williams"
    assert p2.year == 2020
    assert p2.citations == 25


def test_parse_google_scholar_profile_html():
    papers = parse_google_scholar_profile_html(SAMPLE_PROFILE_HTML)
    assert len(papers) == 2

    p1 = papers[0]
    assert p1.title == "Profile Paper One"
    assert p1.author_string == "A Smith, B Jones"
    assert p1.journal == "Nature Medicine"
    assert p1.year == 2023
    assert p1.citations == 142
    assert p1.url == "https://scholar.google.com/citations?view_op=view_citation&user=U1&citation_for_view=ABC"

    p2 = papers[1]
    assert p2.url == "https://example.org/full"


def _provider_with_fetch(monkeypatch, fetch_fn):
    import pop_linux.providers.google_scholar as gs_module

    provider = GoogleScholarProvider()
    monkeypatch.setattr(provider, "_fetch_scholar", fetch_fn)
    monkeypatch.setattr(gs_module, "load_config", lambda: {"google_scholar_timeout": 25})
    monkeypatch.setattr(gs_module, "load_cookies", lambda: {})
    return provider


async def test_search_profile_paginates_until_empty(monkeypatch):
    seen_calls: list = []
    calls = {"n": 0}

    async def fake_fetch(client, url, params, cookies=None):
        seen_calls.append(params)
        calls["n"] += 1
        return SAMPLE_PROFILE_HTML if calls["n"] == 1 else "<html></html>"

    provider = _provider_with_fetch(monkeypatch, fake_fetch)
    result = await provider.search_profile("user1", limit=10)

    assert result.total_found == 2  # only the first non-empty page
    assert [p["cstart"] for p in seen_calls] == [0, 10]


async def test_search_profile_pagination_capped_at_two_times_limit(monkeypatch):
    seen_calls: list = []

    async def fake_fetch(client, url, params, cookies=None):
        seen_calls.append(params)
        return SAMPLE_PROFILE_HTML  # always non-empty -> must hit the cap

    provider = _provider_with_fetch(monkeypatch, fake_fetch)
    result = await provider.search_profile("user1", limit=10)

    assert result.total_found == 4  # 2 papers per page x 2 pages (cap at limit * 2)
    assert [p["cstart"] for p in seen_calls] == [0, 10]


async def test_search_profile_applies_year_and_citation_filters(monkeypatch):
    async def fake_fetch(client, url, params, cookies=None):
        return SAMPLE_PROFILE_HTML

    provider = _provider_with_fetch(monkeypatch, fake_fetch)
    result = await provider.search_profile("user1", limit=10, year_from=2022, min_citations=30)

    assert result.papers
    assert all(p.year >= 2022 and p.citations >= 30 for p in result.papers)
    assert all("Profile Paper Two" not in p.title for p in result.papers)
