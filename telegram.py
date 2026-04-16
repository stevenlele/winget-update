import json
from typing import override

from common import UpdateArgs, Version, get
from github import get_gh_api
from manifest import Installer, fill_sha256_cache
from with_release_notes import WithReleaseNotes


def main():
    Telegram().main()


def _get_installers(new_version: str, is_arm_updated: bool, github_release: dict | None):
    installers: list[Installer] = []

    for arch, url in [
        ("x64", f"https://td.telegram.org/tx64/tsetup-x64.{new_version}.exe"),
        ("x86", f"https://td.telegram.org/tsetup/tsetup.{new_version}.exe"),
        ("arm64", f"https://td.telegram.org/tarm64/tsetup-arm64.{new_version}.exe"),
    ]:
        if arch != "arm64" or is_arm_updated:
            installers.append({
                "Architecture": arch,
                "InstallerType": "inno",
                "Scope": "user",
                "InstallerUrl": url,
                "InstallerSha256": "",
                "UpgradeBehavior": "install",
            })

    for arch, url in [
        ("x64", f"https://td.telegram.org/tx64/tportable-x64.{new_version}.zip"),
        ("x86", f"https://td.telegram.org/tsetup/tportable.{new_version}.zip"),
        ("arm64", f"https://td.telegram.org/tarm64/tportable-arm64.{new_version}.zip"),
    ]:
        if arch != "arm64" or is_arm_updated:
            installers.append({
                "Architecture": arch,
                "InstallerType": "zip",
                "NestedInstallerType": "portable",
                "NestedInstallerFiles": [{
                    "RelativeFilePath": "Telegram\\Telegram.exe",
                    "PortableCommandAlias": "Telegram.exe",
                }],
                "InstallerUrl": url,
                "InstallerSha256": "",
            })

    if not github_release:
        return installers

    # from github_releases.py
    urls: dict[str, str] = {
        asset["name"]: asset["browser_download_url"] for asset in github_release["assets"]
    }
    mapped = [urls.get(installer["InstallerUrl"].rpartition("/")[-1]) for installer in installers]
    if all(mapped):
        fill_sha256_cache(github_release)
        for installer, url in zip(installers, mapped):
            assert url
            installer["InstallerUrl"] = url

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
    args["override_old_installers"] = True
    return args


class Telegram(WithReleaseNotes):
    @override
    def __init__(self) -> None:
        super().__init__(__name__, "Telegram.TelegramDesktop")
        self.installers = None

    @override
    def get_latest_version(self) -> Version:
        v, self.is_arm_updated = get_latest_version()
        return v

    @override
    def has_release_notes(self) -> bool:
        self.github_release = (github_release := _get_github_release(self.version))
        return github_release is not None

    @override
    def get_installers(self) -> list[Installer]:
        if not self.installers:
            self.installers = _get_installers(
                self.version, self.is_arm_updated, self.github_release
            )
        return self.installers

    @override
    def get_update_args(self) -> UpdateArgs:
        return _get_update_args(self.github_release, self.old_version)

    @override
    def should_force_rerun(self) -> bool:
        result = False
        memo: dict = self.memo
        if not memo["is_arm_updated"] and self.is_arm_updated:
            result = True
        if not (is_github_release := memo["is_github_release"]):
            is_github_release = "github.com" in self.get_installers()[0]["InstallerUrl"]
            if is_github_release:
                result = True
        self.memo = {
            "is_arm_updated": self.is_arm_updated,
            "is_github_release": is_github_release,
        }
        return result


def get_latest_version() -> tuple[Version, bool]:
    response = json.loads(get("https://td.telegram.org/current4"))

    win64_stable = response["win64"]["stable"]
    win32_stable = response["win"]["stable"]

    assert (version_code := win64_stable["released"]) == win32_stable["released"]
    is_arm_updated = version_code == response["winarm"]["stable"]

    major_minor, patch = divmod(int(version_code), 1_000)
    major, minor = divmod(major_minor, 1_000)

    return Version((major, minor, patch)), is_arm_updated


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
