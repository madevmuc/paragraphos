# Contributing to Paragraphos

Short guide for anyone (human or agent) sending a patch.

## Guardrails

1. **Privacy first.** Nothing in `core/` may call a third-party service
   beyond what's already there (RSS hosts, podcast CDNs,
   huggingface.co). No analytics, no telemetry, no auto-upload.
2. **TDD.** Every behaviour change ships with a failing test first, then
   the fix. UI-only changes get an offscreen Qt smoke test.
3. **No new runtime dependencies** without a written justification in
   the PR. PyQt6 + stdlib + the libraries already pinned in
   `requirements.txt` cover everything we need.
4. **macOS is the target.** Code that can't run on Apple Silicon +
   macOS 14+ should live behind a feature flag, not in the main path.

## Setup

```bash
git clone <repo>
cd paragraphos
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r dev-requirements.txt
```

Run the test suite:

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

Run the app from source (alias mode — changes live-reload on next
launch):

```bash
PYTHONPATH=. .venv/bin/python app.py
```

Build a standalone `.app`:

```bash
.venv/bin/python setup-full.py py2app
open dist/Paragraphos.app
```

## Code style

- **Formatting**: stick to the surrounding file's style. A pre-commit
  hook with `ruff` will land in Phase 5 — until then, run it manually
  if you have it.
- **Imports**: standard lib → third party → `core` → `ui`. One blank
  line between groups.
- **Type hints** on public functions. `from __future__ import annotations`
  at the top.
- **Docstrings** on every public function or class that isn't trivially
  obvious. Write them so a stranger can skim the module.
- **Comments explain WHY**, not WHAT. No `# increment counter` noise.
- **Tests**: one test file per module, `test_<module>.py`. Use
  `tmp_path`, `respx` for HTTP, `unittest.mock.patch` for subprocess.

## Commit messages

Follow the existing log:

```
<type>: <short description>

Longer body explaining why + context.

Bullet lists for nested changes.
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Reporting a security issue

Open a private email or GitHub security advisory rather than a public
issue. See the `About → Security` tab in the app for the current threat
model.

## Where to start

- Pick a task from `docs/ROADMAP.md` that says `planned`.
- Read the full task block — it lists the exact files to touch.
- Check the latest CHANGELOG entry to see how recent work was commit-staged.
- Keep PRs small and focused. One task = one PR is ideal.
