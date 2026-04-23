import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_dialog_previews_count(tmp_path: Path):
    import PyQt6.QtWidgets as qtw

    _ = qtw.QApplication.instance() or qtw.QApplication([])
    from ui.import_folder_dialog import ImportFolderDialog

    root = tmp_path / "pile"
    root.mkdir()
    (root / "a.wav").write_bytes(b"x")
    (root / "b.mp4").write_bytes(b"x")
    (root / "notes.txt").write_bytes(b"x")

    d = ImportFolderDialog(parent=None)
    d._folder = root  # test hook
    count = d._count_supported(root, recursive=True)
    assert count == 2
