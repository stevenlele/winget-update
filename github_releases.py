from collections.abc import Callable, Sequence
from typing import Protocol

from common import Version, run_komac
from github import create_fork, get_gh_api, update
from manifest import Installer, sha256_cache


class _PackageGetter(Protocol):
    def __call__(self, version: str, urls: dict[str, str]) -> dict[str, Sequence[Installer]]: ...


def main(
    *,
    identifier: str,
    installers: Sequence[Installer],
    locale: str,
    moniker: str,
    owner_and_repo: str,
    pre_release: bool = False,
    transform_release_notes: Callable[[str], str] | None = None,
    use_komac: bool = False,
    with_multiple_packages: _PackageGetter | None = None,
):
    with open(f"{moniker}.txt") as f:
        old_version = Version(f.read())

    if pre_release:
        release = get_gh_api(f"/repos/{owner_and_repo}/releases")[0]
    else:
        release = get_gh_api(f"/repos/{owner_and_repo}/releases/latest")

    for asset in release["assets"]:
        if digest := asset.get("digest"):
            sha256_cache[asset["browser_download_url"]] = digest.removeprefix("sha256:").upper()

    version: str = release["tag_name"].removeprefix("v")
    if (new_version := Version(version)) == old_version:
        return

    assert new_version > old_version

    urls: dict[str, str] = {
        asset["name"]: asset["browser_download_url"] for asset in release["assets"]
    }

    for installer in installers:
        filename = installer["InstallerUrl"].format(version=version)
        installer["InstallerUrl"] = urls[filename]

    if not use_komac:
        release_notes: str = release["body"]
        if transform_release_notes is not None:
            release_notes = transform_release_notes(release_notes)

        if with_multiple_packages is None:
            packages = {identifier: installers}
        else:
            packages = with_multiple_packages(version, urls)

        for identifier, installers in packages.items():
            update(
                identifier,
                version,
                installers,
                {
                    "base_version": f"{old_version}",
                    "owner_and_repo": owner_and_repo,
                    "release_notes": {locale: (release_notes, release["html_url"])},
                    "override_old_installers": bool(with_multiple_packages),
                },
            )
    else:
        create_fork()
        run_komac(identifier, version, [installer["InstallerUrl"] for installer in installers])

    with open(f"{moniker}.txt", "w") as f:
        f.write(version)
