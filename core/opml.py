"""OPML import — parse podcast subscription export files."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List
try:
    from defusedxml import ElementTree as ET  # type: ignore
except ImportError:  # pragma: no cover — bundled install always has defusedxml
    from xml.etree import ElementTree as ET  # type: ignore


def parse_opml(path: Path) -> List[Dict[str, str]]:
    """Extract {title, xmlUrl} entries from an OPML subscription file.

    Uses defusedxml to block XXE / billion-laughs / external-entity attacks
    a malicious OPML file could otherwise exploit.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    out: List[Dict[str, str]] = []
    for node in root.iter("outline"):
        xml_url = node.get("xmlUrl")
        if not xml_url:
            continue
        out.append({
            "title": node.get("title") or node.get("text", "untitled"),
            "xmlUrl": xml_url,
        })
    return out
