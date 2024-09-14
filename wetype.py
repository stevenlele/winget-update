import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import override
from zoneinfo import ZoneInfo

from common import VERSION_REGEX, UpdateArgs, Version, get
from manifest import Installer
from with_release_notes import WithReleaseNotes


def main():
    WeType().main()


def _get_latest_version():
    app_info = json.loads(get("https://z.weixin.qq.com/web/api/app_info"))
    url: str = app_info["data"]["windows"]["latest"]
    assert (match := VERSION_REGEX.search(url))
    new_version = Version(match.group())
    return new_version, url


def _get_release(new_version: str) -> dict | None:
    changelog_html = get("https://z.weixin.qq.com/web/change-log/")
    start = changelog_html.index(pre := "window.injectData=") + len(pre)
    end = changelog_html.index("</script>", start)
    changelog: list = json.loads(changelog_html[start:end])["appChangelog"]

    short_version = str(new_version).rpartition(".")[0]
    try:
        release = next(r for r in changelog if r["platform"] == 4 and r["version"] == short_version)
    except StopIteration:
        release = None
    return release


def _get_update_args(release: dict | None, short_version: str):
    if not release:
        args: UpdateArgs = {
            "release_notes_locale": "zh-CN",
            "keep_notes_on_version_prefix": f"{short_version}.",
        }
    else:
        # release_date = datetime.fromtimestamp(release["release_date"], ZoneInfo("Asia/Shanghai"))

        release_notes = "\n".join(
            text
            for element in ET.fromstring(f"<body>{release['content_html']}</body>")
            if (text := element.text) and (text := text.strip()) and text != "该版本主要更新"
        )
        release_notes = release_notes.replace("」 ", "」")

        args: UpdateArgs = {
            "release_notes": release_notes,
            "release_notes_locale": "zh-CN",
            "release_notes_url": f"https://z.weixin.qq.com/web/change-log/{release['id']}",
            # "release_date": release_date.date(),
            "is_url_important": True,
        }
    return args


class WeType(WithReleaseNotes):
    def __init__(self) -> None:
        super().__init__(__name__, "Tencent.WeType")

    @override
    def get_installers(self) -> list[Installer]:
        url = self.url
        return [
            {"Architecture": "x64", "InstallerUrl": url},
            {"Architecture": "arm64", "InstallerUrl": url},
        ]

    @override
    def get_latest_version(self) -> Version:
        latest_version, self.url = _get_latest_version()
        return latest_version

    @override
    def has_release_notes(self) -> bool:
        self.release = (release := _get_release(self.version))
        return bool(release)

    @override
    def get_update_args(self) -> UpdateArgs:
        return _get_update_args(self.release, self.version.rpartition(".")[0])
