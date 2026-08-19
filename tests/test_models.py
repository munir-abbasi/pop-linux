from pop_linux.models import Paper, Author
from pop_linux.config import load_config, update_config_value


def test_author_model():
    author = Author(name="Jane Doe", affiliation="PolyU", author_id="A123")
    assert author.name == "Jane Doe"
    assert author.affiliation == "PolyU"
    assert author.author_id == "A123"


def test_paper_model():
    paper = Paper(
        title="Test Paper Title",
        authors=[Author(name="Author One"), Author(name="Author Two")],
        year=2024,
        journal="Journal of Testing",
        citations=42,
        doi="10.1234/test.5678"
    )
    assert paper.title == "Test Paper Title"
    assert paper.author_string == "Author One, Author Two"
    assert paper.author_count == 2
    assert paper.citations == 42


def test_paper_empty_authors():
    paper = Paper(title="Single Author Spec")
    assert paper.author_string == "Unknown"
    assert paper.author_count == 1


def test_config_operations(tmp_path, monkeypatch):
    test_config_dir = tmp_path / "pop_linux"
    test_config_file = test_config_dir / "config.toml"
    monkeypatch.setattr("pop_linux.config.CONFIG_DIR", test_config_dir)
    monkeypatch.setattr("pop_linux.config.CONFIG_FILE", test_config_file)

    cfg = load_config()
    assert cfg["default_provider"] == "openalex"
    assert test_config_file.exists()

    updated = update_config_value("default_provider", "semanticscholar")
    assert updated["default_provider"] == "semanticscholar"

    reloaded = load_config()
    assert reloaded["default_provider"] == "semanticscholar"
