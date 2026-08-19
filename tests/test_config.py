from pop_linux import config as cfg


def test_load_config_defaults(tmp_path):
    cfg.CONFIG_DIR = tmp_path
    cfg.CONFIG_FILE = tmp_path / "config.toml"
    cfg.save_config(cfg.DEFAULT_CONFIG)
    loaded = cfg.load_config()
    assert loaded["default_limit"] == 50
    assert loaded["google_scholar_timeout"] == 30
    assert loaded["api_keys"] == {"semanticscholar": "", "ncbi": ""}


def test_load_config_coerces_invalid_int_keys_to_defaults(tmp_path):
    cfg.CONFIG_DIR = tmp_path
    cfg.CONFIG_FILE = tmp_path / "config.toml"
    cfg.save_config({**cfg.DEFAULT_CONFIG, "default_limit": "abc", "google_scholar_timeout": "oops"})
    loaded = cfg.load_config()
    assert loaded["default_limit"] == 50
    assert loaded["google_scholar_timeout"] == 30


def test_load_config_coerces_numeric_strings(tmp_path):
    cfg.CONFIG_DIR = tmp_path
    cfg.CONFIG_FILE = tmp_path / "config.toml"
    cfg.save_config({**cfg.DEFAULT_CONFIG, "default_limit": "25"})
    loaded = cfg.load_config()
    assert loaded["default_limit"] == 25


def test_load_config_tolerates_float_for_int_keys(tmp_path):
    cfg.CONFIG_DIR = tmp_path
    cfg.CONFIG_FILE = tmp_path / "config.toml"
    cfg.save_config({**cfg.DEFAULT_CONFIG, "google_scholar_timeout": 12.9})
    loaded = cfg.load_config()
    assert loaded["google_scholar_timeout"] == 12


def test_load_config_malformed_api_keys_falls_back_to_defaults(tmp_path):
    cfg.CONFIG_DIR = tmp_path
    cfg.CONFIG_FILE = tmp_path / "config.toml"
    cfg.save_config({**cfg.DEFAULT_CONFIG, "api_keys": "malformed-string"})
    loaded = cfg.load_config()
    assert loaded["api_keys"] == {"semanticscholar": "", "ncbi": ""}


def test_load_config_merges_valid_api_keys(tmp_path):
    cfg.CONFIG_DIR = tmp_path
    cfg.CONFIG_FILE = tmp_path / "config.toml"
    cfg.save_config({**cfg.DEFAULT_CONFIG, "api_keys": {"ncbi": "MYKEY"}})
    loaded = cfg.load_config()
    assert loaded["api_keys"] == {"semanticscholar": "", "ncbi": "MYKEY"}
