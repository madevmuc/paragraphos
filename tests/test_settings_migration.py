from core.models import Settings, backfill_setup_completed


def test_fresh_defaults_have_flag_false():
    assert Settings().setup_completed is False


def test_backfill_flips_flag_when_output_root_customised():
    s = Settings()
    s.output_root = "/Users/alice/Transcripts"
    backfill_setup_completed(s)
    assert s.setup_completed is True


def test_backfill_leaves_flag_false_on_pure_defaults():
    s = Settings()
    backfill_setup_completed(s)
    assert s.setup_completed is False


def test_backfill_respects_existing_true():
    s = Settings()
    s.setup_completed = True
    # Even with pure defaults + flag already True, don't flip back.
    backfill_setup_completed(s)
    assert s.setup_completed is True


def test_backfill_flips_flag_when_obsidian_vault_path_customised():
    s = Settings()
    s.obsidian_vault_path = "/Users/alice/ObsidianVault"
    backfill_setup_completed(s)
    assert s.setup_completed is True


def test_backfill_flips_flag_when_knowledge_hub_root_customised():
    s = Settings()
    s.knowledge_hub_root = "/Users/alice/knowledge-hub"
    backfill_setup_completed(s)
    assert s.setup_completed is True
