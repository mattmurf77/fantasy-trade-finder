"""The shipped iOS version comes from Info.plist, NOT app.json.

`mobile/ios/` is committed (bare workflow), so EAS reads
`CFBundleShortVersionString` and ignores `expo.version`. On 2026-08-19 a
release bumped `app.json` to 1.15.0 alone and the build went to TestFlight
labelled 1.14.0 — the binary was correct, the version string was not.

Nothing else catches this: the build succeeds, the submission succeeds, and
the wrong number only shows up in App Store Connect after ~25 minutes.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP_JSON = REPO / "mobile/app.json"
INFO_PLIST = REPO / "mobile/ios/DTFDynastyTradeFinder/Info.plist"


def _plist_short_version() -> str:
    text = INFO_PLIST.read_text()
    m = re.search(
        r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", text)
    assert m, "CFBundleShortVersionString not found in Info.plist"
    return m.group(1).strip()


def test_app_json_and_info_plist_versions_agree():
    app_version = json.loads(APP_JSON.read_text())["expo"]["version"]
    plist_version = _plist_short_version()
    assert app_version == plist_version, (
        f"mobile/app.json expo.version is {app_version!r} but "
        f"Info.plist CFBundleShortVersionString is {plist_version!r}. "
        "EAS ships the Info.plist value — bump BOTH or the build is mislabelled."
    )
