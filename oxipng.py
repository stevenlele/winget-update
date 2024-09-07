import github_releases


def main():
    github_releases.main(
        identifier="Shssoichiro.Oxipng",
        installers=[
            {"InstallerUrl": "oxipng-{version}-i686-pc-windows-msvc.zip"},
            {"InstallerUrl": "oxipng-{version}-x86_64-pc-windows-msvc.zip"},
        ],
        locale="en-US",
        moniker=__name__,
        owner_and_repo="shssoichiro/oxipng",
        use_komac=True,
    )
