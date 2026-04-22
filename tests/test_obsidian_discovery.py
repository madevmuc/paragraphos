from core.obsidian import best_guess_vault, discover_vaults, is_obsidian_vault


def test_is_obsidian_vault_true(tmp_path):
    v = tmp_path / "MyVault"
    v.mkdir()
    (v / ".obsidian").mkdir()
    assert is_obsidian_vault(v)


def test_is_obsidian_vault_false_without_dotdir(tmp_path):
    v = tmp_path / "NotVault"
    v.mkdir()
    assert not is_obsidian_vault(v)


def test_discover_vaults_finds_one_under_extra_root(tmp_path):
    v = tmp_path / "MyVault"
    v.mkdir()
    (v / ".obsidian").mkdir()
    found = discover_vaults(extra_roots=[tmp_path])
    assert v.resolve() in [p.resolve() for p in found]


def test_discover_vaults_returns_empty_when_nothing(tmp_path):
    # Restrict roots so home-dir vaults don't pollute the result.
    import core.obsidian as mod

    saved = mod._LIKELY_ROOTS
    mod._LIKELY_ROOTS = []
    try:
        assert discover_vaults(extra_roots=[tmp_path]) == []
    finally:
        mod._LIKELY_ROOTS = saved


def test_best_guess_vault_returns_first_or_none(monkeypatch, tmp_path):
    v = tmp_path / "Vault"
    v.mkdir()
    (v / ".obsidian").mkdir()
    monkeypatch.setattr("core.obsidian._LIKELY_ROOTS", [tmp_path])
    assert best_guess_vault() == v


def test_best_guess_vault_none_when_no_vaults(monkeypatch, tmp_path):
    monkeypatch.setattr("core.obsidian._LIKELY_ROOTS", [tmp_path])
    assert best_guess_vault() is None
