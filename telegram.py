import json

from common import *


def main():
    with open("telegram.json") as f:
        old_version_data: VersionData = json.load(f)

    old_version = Version(old_version_data["version"])

    new_version = get_latest_version()
    github_release = get_github_release(new_version)

    if old_version == new_version:
        if github_release and old_version_data["has_release_notes"]:
            raise NotImplementedError
        return

    assert new_version > old_version

    urls = (
        f"https://td.telegram.org/tx64/tsetup-x64.{new_version}.exe",
        f"https://td.telegram.org/tsetup/tsetup.{new_version}.exe",
        f"https://td.telegram.org/tx64/tportable-x64.{new_version}.zip",
        f"https://td.telegram.org/tsetup/tportable.{new_version}.zip",
    )

    assert all(CLIENT.head(url).is_success for url in urls)

    if github_release:
        args: KomacArgs = {
            "owner": "telegramdesktop",
            "repo": "tdesktop",
            "release_notes": base64_encode(github_release["body"]),
            "release_notes_url": github_release["html_url"],
            "release_notes_locale": "en-US",
        }
    else:
        args = {}

    run_komac("Telegram.TelegramDesktop", f"{new_version}", urls, args)

    with open("telegram.json", "w") as f:
        new_version_data: VersionData = {
            "version": f"{new_version}",
            "has_release_notes": bool(github_release),
        }
        json.dump(new_version_data, f, separators=(",", ":"))


def get_latest_version() -> Version:
    response = json.loads(get("https://td.telegram.org/current4"))

    win64_stable = response["win64"]["stable"]
    win32_stable = response["win"]["stable"]

    assert (
        (version_code := win64_stable["released"])
        == win64_stable["testing"]
        == win32_stable["released"]
        == win32_stable["testing"]
    )

    major, minor_patch = divmod(int(version_code), 1_000_000)
    minor, patch = divmod(minor_patch, 1_000)

    return Version((major, minor, patch))


def get_github_release(latest_version: Version) -> dict | None:
    releases = get_gh_api("https://api.github.com/repos/telegramdesktop/tdesktop/releases")
    tag_name = f"v{latest_version}"
    try:
        index = next(i for i, r in enumerate(releases) if r["tag_name"] == tag_name)
    except StopIteration:
        return None
    for i in range(index):
        assert all("Windows" not in asset["label"] for asset in releases[i]["assets"])
    return releases[index]
