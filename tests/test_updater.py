import plistlib

from app import updater


def test_version_comparison_handles_v_prefixes():
    assert updater._version_gt("v0.3.4", "0.3.3")
    assert updater._version_gt("0.4.0", "0.3.9")
    assert not updater._version_gt("0.3.3", "0.3.3")
    assert not updater._version_gt("0.3.2", "0.3.3")


def test_current_version_reads_app_info_plist(monkeypatch, tmp_path):
    app_path = tmp_path / "Email Assistant.app"
    contents = app_path / "Contents"
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleShortVersionString": "1.2.3"}, f)

    monkeypatch.setattr(updater, "get_app_path", lambda: str(app_path))
    monkeypatch.delattr(updater.sys, "_MEIPASS", raising=False)

    assert updater.get_current_version() == "1.2.3"
