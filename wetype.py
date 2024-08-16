import json
from datetime import datetime
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from common import *


def main():
    with open("wetype.txt") as f:
        old_version = Version(f.read())

    app_info = json.loads(get("https://z.weixin.qq.com/web/api/app_info"))
    url: str = app_info["data"]["windows"]["latest"]
    assert (match := VERSION_REGEX.search(url))
    new_version = Version(match.group())

    if new_version == old_version:
        return
    assert new_version > old_version

    changelog_html = get("https://z.weixin.qq.com/web/change-log/")
    start = changelog_html.index(pre := "window.injectData=") + len(pre)
    end = changelog_html.index("</script>", start)
    changelog: list = json.loads(changelog_html[start:end])["appChangelog"]

    short_version = str(new_version).rpartition(".")[0]
    try:
        release = next(r for r in changelog if r["platform"] == 4 and r["version"] == short_version)
    except StopIteration:
        args: KomacArgs = {}
    else:
        release_date = datetime.fromtimestamp(release["release_date"], ZoneInfo("Asia/Shanghai"))

        release_notes = "\n".join(
            text
            for element in ET.fromstring(f"<body>{release['content_html']}</body>")
            if (text := element.text) and (text := text.strip()) and text != "该版本主要更新"
        )

        args: KomacArgs = {
            "release_notes": base64_encode(release_notes),
            "release_notes_locale": "zh-CN",
            "release_notes_url": f"https://z.weixin.qq.com/web/change-log/{release['id']}",
            "release_date": f"{release_date:%Y-%m-%d}",
        }

    run_komac("Tencent.WeType", str(new_version), url, args)

    with open("wetype.txt", "w") as f:
        f.write(str(new_version))
