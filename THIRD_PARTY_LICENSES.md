# Third-party licenses

Paragraphos itself is licensed under [MIT](LICENSE). It bundles or
depends on the following third-party components.

This file is the canonical reference. The in-app **About → Credits &
Licenses** dialog mirrors the same data, and the README shows a short
summary.

## Direct Python dependencies (declared in `requirements.txt`)

| Component       | Version  | License                            | URL                                                       |
| --------------- | -------- | ---------------------------------- | --------------------------------------------------------- |
| PyQt6           | ≥ 6.6    | GPL-3.0 OR Riverbank Commercial    | https://www.riverbankcomputing.com/software/pyqt/         |
| APScheduler     | ≥ 3.10   | MIT                                | https://apscheduler.readthedocs.io/                       |
| watchdog        | ≥ 4.0    | Apache-2.0                         | https://github.com/gorakhargosh/watchdog                  |
| feedparser      | ≥ 6.0    | BSD-2-Clause                       | https://github.com/kurtmckee/feedparser                   |
| httpx           | ≥ 0.27   | BSD-3-Clause                       | https://www.python-httpx.org/                             |
| PyYAML          | ≥ 6.0    | MIT                                | https://pyyaml.org/                                       |
| pydantic        | ≥ 2.6    | MIT                                | https://docs.pydantic.dev/                                |
| beautifulsoup4  | ≥ 4.12   | MIT                                | https://www.crummy.com/software/BeautifulSoup/            |
| lxml            | ≥ 5.0    | BSD-3-Clause                       | https://lxml.de/                                          |
| defusedxml      | ≥ 0.7    | PSF-2.0                            | https://github.com/tiran/defusedxml                       |

## Transitive Python deps pinned for py2app bundling

| Component | Version  | License      |
| --------- | -------- | ------------ |
| sniffio   | ≥ 1.3    | MIT/Apache-2 |
| anyio     | ≥ 4.0    | MIT          |
| h11       | ≥ 0.14   | MIT          |
| httpcore  | ≥ 1.0    | BSD-3-Clause |
| pytz      | ≥ 2024.1 | MIT          |
| tzlocal   | ≥ 5.0    | MIT          |

## Native binaries / external tools

| Component   | License                          | How it ships                                                                                                                                    |
| ----------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Python      | PSF-2.0                          | Bundled by py2app inside the `.app`.                                                                                                            |
| whisper.cpp | MIT                              | Installed via Homebrew (`brew install whisper-cpp`) on first run; not bundled.                                                                  |
| ffmpeg      | LGPL-2.1 / GPL (Homebrew build)  | Installed via Homebrew on first run; not bundled. Used by yt-dlp for muxing audio downloads.                                                    |
| Homebrew    | BSD-2-Clause                     | Used as the package manager during first-run setup; not bundled.                                                                                |
| **yt-dlp**  | **Unlicense (public domain)**    | **Lazy-installed at runtime to `~/Library/Application Support/Paragraphos/bin/yt-dlp` from the official GitHub Releases. Not bundled in the .app.** |

## Models / data

| Component                                | License                               | Notes                                                                                                                                  |
| ---------------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| OpenAI Whisper model weights (large-v3-turbo) | MIT                              | Downloaded separately from the Hugging Face mirror at `huggingface.co/ggerganov/whisper.cpp` on first run. SHA-256 verified.           |
| Podcast / YouTube audio + captions       | Property of original publishers       | Paragraphos transcribes for personal research / archiving. Check each source's terms before redistribution.                            |

## License compatibility — PyQt6 (the non-trivial one)

PyQt6 is dual-licensed: **GPL-3.0** OR a **Riverbank Commercial**
licence. Paragraphos itself is MIT.

- For **personal / source-available use** (the current distribution
  surface — the maintainer's own machines + an unsigned `.app` shared
  with a small audience under the MIT licence with full source
  available), MIT-licensed code linked against GPL-3.0 PyQt6 is fine:
  the *combined work* must be redistributed under GPL-3.0-compatible
  terms, and MIT is GPL-compatible. Distributing the `.app` is therefore
  effectively a GPL-3.0 distribution of the combined work; the MIT
  source remains MIT in isolation.
- For **closed-source / commercial redistribution** without the GPL
  obligations (full source, no additional restrictions, etc.), a
  Riverbank Commercial PyQt6 licence is required.

This is not a conflict at the current scale, but anyone repackaging
Paragraphos for closed-source distribution must purchase a Riverbank
licence or migrate the UI to a non-GPL Qt binding (e.g. PySide6 under
LGPL).

## yt-dlp distribution note

Paragraphos does not bundle yt-dlp. On first YouTube ingest the app
fetches the latest `yt-dlp_macos` from the official GitHub release URL
(`https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos`)
into the user's Application Support directory, then invokes it as a
subprocess. yt-dlp is released into the public domain under the
[Unlicense](https://unlicense.org/), so no attribution or license-file
shipping is strictly required, but it is credited in the About dialog
and here for transparency.
