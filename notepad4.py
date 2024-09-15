import re
from collections.abc import Sequence

from manifest import Installer


def main():
    from github_releases import main

    main(
        identifier="",
        installers=(),
        locale="en-US",
        moniker=__name__,
        owner_and_repo="zufuliu/notepad4",
        transform_release_notes=_transform,
        with_multiple_packages=_get_packages,
    )


def _get_packages(version: str, urls: dict[str, str]) -> dict[str, Sequence[Installer]]:
    version = f"v{version}"
    urls = {file: url for file, url in urls.items() if not file.startswith("FindInFiles-")}

    installers: list[Installer] = []
    installers_avx2: list[Installer] = []

    def get_installer(url: str, lang: str, arch: str) -> Installer:
        if lang == "i18n":
            return {
                "Architecture": arch,
                "InstallerUrl": url,
            }
        else:
            return {
                "InstallerLocale": lang,
                "Architecture": arch,
                "InstallerUrl": url,
            }

    for lang in ("en", "fr", "it", "ja", "ko", "zh-Hans", "zh-Hant", "i18n"):
        for arch, asset_arch in (
            ("x86", "Win32"),
            ("x64", "x64"),
            ("arm", "ARM"),
            ("arm64", "ARM64"),
        ):
            url = urls.pop(f"Notepad4_{lang}_{asset_arch}_{version}.zip", None)
            if url is None:
                assert arch == "arm" and lang != "en"
                continue
            url = urls.pop(f"Notepad4_HD_{lang}_{asset_arch}_{version}.zip", url)
            installers.append(get_installer(url, lang, arch))

        arch, asset_arch = "x64", "AVX2"
        del urls[f"Notepad4_{lang}_{asset_arch}_{version}.zip"]
        url = urls.pop(f"Notepad4_HD_{lang}_{asset_arch}_{version}.zip")
        installers_avx2.append(get_installer(url, lang, arch))

    assert not urls, urls

    return {"zufuliu.notepad4": installers, "zufuliu.notepad4.AVX2": installers_avx2}


def _transform(release_notes: str) -> str:
    _, release_notes = re.split(r"#+ Changes Since .+", release_notes)
    release_notes = re.sub(r"#+ File List.+", "", release_notes, flags=re.DOTALL)
    release_notes = re.sub(r"[,:]? ?[0-9a-f]{40}(?: and|, etc\.?)?", "", release_notes)  # SHA
    release_notes = re.sub(r"(?<!\.)\.\.(?=\s|$)", ".", release_notes, flags=re.MULTILINE)  # . SHA.
    release_notes = release_notes.replace(" ()", "")  # (SHA)
    release_notes = re.sub(r"</?kbd>", "`", release_notes)
    return release_notes
