# Integration tests

Opt-in, `@pytest.mark.integration`-marked tests that drive the full
pipeline end-to-end: RSS fetch → download → whisper → md.

```bash
PYTHONPATH=. .venv/bin/pytest -m integration
```

## What's needed

1. **whisper-cpp installed** (`brew install whisper-cpp`).
2. **A small model** — `ggml-base.bin` or `ggml-tiny.bin` is fine for
   these; fidelity isn't the point. Drop it under
   `~/.config/open-wispr/models/`.
3. **A real short MP3** as `fixtures/short.mp3` — ideally <30 s,
   royalty-free. Not committed to keep the repo small; CI pulls it
   from a known URL (see `conftest.py`).

## Why this exists

The [dotted-slug bug](../../CHANGELOG.md#v043) took hours to track down
because unit tests mocked whisper-cli and the mocks silently adopted
the same buggy `Path.with_suffix()` behaviour as production. An
integration test against the real binary on a real file would have
caught it in seconds.
