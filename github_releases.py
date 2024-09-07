from collections.abc import Callable, Sequence

from common import Version, run_komac
from github import get_gh_api, update
from manifest import Installer


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
):
    with open(f"{moniker}.txt") as f:
        old_version = Version(f.read())

    if pre_release:
        release = get_gh_api(f"/repos/{owner_and_repo}/releases")[0]
    else:
        release = get_gh_api(f"/repos/{owner_and_repo}/releases/latest")

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

    if use_komac:
        run_komac(identifier, version, [installer["InstallerUrl"] for installer in installers])
    else:
        release_notes: str = release["body"]
        if transform_release_notes is not None:
            release_notes = transform_release_notes(release_notes)

        update(
            identifier,
            version,
            installers,
            {
                "owner_and_repo": owner_and_repo,
                "release_notes": release_notes,
                "release_notes_url": release["html_url"],
                "release_notes_locale": locale,
            },
        )

    with open(f"{moniker}.txt", "w") as f:
        f.write(version)
