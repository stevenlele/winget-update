import json
from typing import override

from common import CLIENT, UpdateArgs, Version, get
from github import get_gh_api, update
from manifest import Installer
from with_release_notes import WithReleaseNotes


def main():
    Telegram().main()


def _get_installers(new_version: str):
    installers: list[Installer] = [
        {
            "Architecture": "x64",
            "InstallerType": "inno",
            "Scope": "user",
            "InstallerUrl": f"https://td.telegram.org/tx64/tsetup-x64.{new_version}.exe",
            "UpgradeBehavior": "install",
        },
        {
            "Architecture": "x86",
            "InstallerType": "inno",
            "Scope": "user",
            "InstallerUrl": f"https://td.telegram.org/tsetup/tsetup.{new_version}.exe",
            "UpgradeBehavior": "install",
        },
        {
            "Architecture": "x64",
            "InstallerType": "zip",
            "InstallerUrl": f"https://td.telegram.org/tx64/tportable-x64.{new_version}.zip",
        },
        {
            "Architecture": "x86",
            "InstallerType": "zip",
            "InstallerUrl": f"https://td.telegram.org/tsetup/tportable.{new_version}.zip",
        },
    ]

    assert all(CLIENT.head(installer["InstallerUrl"]).is_success for installer in installers)

    return installers


def _get_update_args(github_release: dict | None, old_version: str):
    if github_release:
        args: UpdateArgs = {
            "base_version": old_version,
            "owner_and_repo": "telegramdesktop/tdesktop",
            "release_notes": {"en-US": (github_release["body"], github_release["html_url"])},
        }
    else:
        args = {"base_version": old_version}
    return args


class Telegram(WithReleaseNotes):
    @override
    def __init__(self) -> None:
        super().__init__(__name__, "Telegram.TelegramDesktop")

    @override
    def get_latest_version(self) -> Version:
        return get_latest_version()

    @override
    def has_release_notes(self) -> bool:
        self.github_release = (github_releases := _get_github_release(self.version))
        return github_releases is not None

    @override
    def get_installers(self) -> list[Installer]:
        return _get_installers(self.version)

    @override
    def get_update_args(self) -> UpdateArgs:
        return _get_update_args(self.github_release, self.old_version)


def get_latest_version() -> Version:
    response = json.loads(get("https://td.telegram.org/current4"))

    win64_stable = response["win64"]["stable"]
    win32_stable = response["win"]["stable"]

    assert (version_code := win64_stable["released"]) == win32_stable["released"]

    major_minor, patch = divmod(int(version_code), 1_000)
    major, minor = divmod(major_minor, 1_000)

    return Version((major, minor, patch))


def _get_github_release(latest_version: str) -> dict | None:
    releases = get_gh_api("https://api.github.com/repos/telegramdesktop/tdesktop/releases")
    tag_name = f"v{latest_version}"
    try:
        index = next(i for i, r in enumerate(releases) if r["tag_name"] == tag_name)
    except StopIteration:
        return None
    for i in range(index):
        if releases[i]["prerelease"]:
            continue
        assert all("Windows" not in asset["label"] for asset in releases[i]["assets"])
    return releases[index]
