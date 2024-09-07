import re

from common import *
from github import get_gh_api, update


def main():
    with open("v2rayn.txt") as f:
        old_version = Version(f.read())

    release = get_gh_api("https://api.github.com/repos/2dust/v2rayN/releases")[0]

    if (new_version := Version(release["tag_name"])) == old_version:
        return

    assert new_version > old_version

    url = next(
        asset["browser_download_url"]
        for asset in release["assets"]
        if asset["name"] == "v2rayN-With-Core.zip"
    )

    release_notes: str = release["body"]
    release_notes = re.sub(r"^#+ 本次更新.*", "", release_notes)
    release_notes = re.sub(r"#+ 注意.+", "", release_notes, flags=re.DOTALL)

    update(
        "2dust.v2rayN",
        f"{new_version}",
        [{"Architecture": "x64", "InstallerUrl": url}],
        {
            "owner": "2dust",
            "repo": "v2rayN",
            "release_notes": release_notes,
            "release_notes_url": release["html_url"],
            "release_notes_locale": "zh-CN",
        },
    )

    with open("v2rayn.txt", "w") as f:
        f.write(str(new_version))
