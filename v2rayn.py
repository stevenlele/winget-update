import re

import github_releases


def _transform(release_notes: str) -> str:
    release_notes = re.sub(r"^#+ 本次更新.*", "", release_notes)
    release_notes = re.sub(r"#+ 注意.+", "", release_notes, flags=re.DOTALL)
    release_notes = re.sub(r"#+ 发布文件介绍.*", "", release_notes, flags=re.DOTALL)
    return release_notes


def main():
    github_releases.main(
        identifier="2dust.v2rayN",
        installers=[{"Architecture": "x64", "InstallerUrl": "v2rayN-windows-64-With-Core.zip"}],
        locale="zh-CN",
        moniker=__name__,
        owner_and_repo="2dust/v2rayN",
        pre_release=True,
        transform_release_notes=_transform,
    )
