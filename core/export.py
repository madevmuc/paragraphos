"""Export a show's transcripts as a ZIP (no audio)."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path


def export_show(slug: str, output_root: Path, export_dir: Path) -> Path:
    """Create <export_dir>/<slug>-YYYY-MM-DD.zip with all .md + .srt."""
    src = Path(output_root) / slug
    export_dir = Path(export_dir).expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    zip_path = export_dir / f"{slug}-{date_str}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pattern in ("*.md", "*.srt"):
            for f in src.rglob(pattern):
                # Skip anything under audio/
                if "audio" in f.parts:
                    continue
                zf.write(f, arcname=f.relative_to(src))
    return zip_path
