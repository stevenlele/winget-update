import re

import github_releases


def main():
    def transform(release_notes: str) -> str:
        release_notes = re.sub(r"^#+ Release Notes.*", "", release_notes)
        release_notes = re.sub(r"#+ Contributors.+", "", release_notes, flags=re.DOTALL)
        release_notes = re.sub(r"\\\[`(.+?)`\\\]", r"[\1]", release_notes)  # \[`module`\]
        release_notes = re.sub(r"`([A-Z]+\d+)`", r"\1", release_notes)  # rules
        return release_notes

    github_releases.main(
        identifier="astral-sh.ruff",
        installers=[
            {"Architecture": "x86", "InstallerUrl": "ruff-i686-pc-windows-msvc.zip"},
            {"Architecture": "x64", "InstallerUrl": "ruff-x86_64-pc-windows-msvc.zip"},
            {"Architecture": "arm64", "InstallerUrl": "ruff-aarch64-pc-windows-msvc.zip"},
        ],
        locale="en-US",
        moniker=__name__,
        owner_and_repo="astral-sh/ruff",
        transform_release_notes=transform,
    )
