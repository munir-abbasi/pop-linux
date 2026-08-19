import pytest
from pop_linux.models import Paper, Author
from pop_linux.utils.metrics import calculate_metrics


def test_calculate_metrics_empty():
    metrics = calculate_metrics([])
    assert metrics.total_papers == 0
    assert metrics.total_citations == 0
    assert metrics.h_index == 0
    assert metrics.g_index == 0


def test_calculate_metrics_known_h_and_g():
    # Citations: 10, 8, 5, 4, 3
    # h-index: 4 (papers with >= 4 citations are 10, 8, 5, 4)
    # g-index: 5 (cumulative citations: 10, 18, 23, 27, 30. 30 >= 5^2 = 25)
    # e-index: sqrt((10-4) + (8-4) + (5-4) + (4-4)) = sqrt(6 + 4 + 1 + 0) = sqrt(11) ≈ 3.32
    # i10-index: 1 (paper with citation 10)
    papers = [
        Paper(title="P1", citations=10, year=2020, authors=[Author(name="A1")]),
        Paper(title="P2", citations=8, year=2021, authors=[Author(name="A1")]),
        Paper(title="P3", citations=5, year=2022, authors=[Author(name="A1")]),
        Paper(title="P4", citations=4, year=2023, authors=[Author(name="A1")]),
        Paper(title="P5", citations=3, year=2024, authors=[Author(name="A1")]),
    ]

    metrics = calculate_metrics(papers)
    assert metrics.total_papers == 5
    assert metrics.total_citations == 30
    assert metrics.avg_citations_per_paper == 6.0
    assert metrics.h_index == 4
    assert metrics.g_index == 5
    assert pytest.approx(metrics.e_index, 0.01) == 3.32
    assert metrics.hL_norm == 4.0
    assert metrics.awcr > 0.0
    assert metrics.aw_index > 0.0
    assert metrics.i10_index == 1
