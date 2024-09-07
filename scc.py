import re

import github_releases


def main():
    def transform(release_notes: str) -> str:
        release_notes = re.sub(r"^#+ Release.*", "", release_notes)
        release_notes = re.sub(r"#+ Changelog.+", "", release_notes, flags=re.DOTALL)
        return release_notes

    github_releases.main(
        identifier="BenBoyter.scc",
        installers=[
            {"Architecture": "x86", "InstallerUrl": "scc_Windows_i386.zip"},
            {"Architecture": "x64", "InstallerUrl": "scc_Windows_x86_64.zip"},
            {"Architecture": "arm64", "InstallerUrl": "scc_Windows_arm64.zip"},
        ],
        locale="en-US",
        moniker=__name__,
        owner_and_repo="boyter/scc",
        transform_release_notes=transform,
    )
