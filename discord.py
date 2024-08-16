import json

from common import *


def main():
    with open("discord.txt") as f:
        x64, x86 = map(int, f.read().split(","))
        versions = {"x64": x64, "x86": x86}

    for arch, old_version in versions.items():
        url = f"https://updates.discord.com/distributions/app/manifests/latest?channel=stable&platform=win&arch={arch}"
        triple: list[int] = json.loads(get(url))["full"]["host_version"]
        assert triple[:2] == [1, 0]
        assert (new_version := triple[2]) >= old_version
        if new_version > old_version:
            run_komac(
                "Discord.Discord",
                f"1.0.{new_version}",
                f"https://dl.discordapp.net/distro/app/stable/win/{arch}/1.0.{new_version}/DiscordSetup.exe",
                {"base_version": f"1.0.{old_version}"},
            )
            versions[arch] = new_version

    with open("discord.txt", "w") as f:
        f.write(f"{versions['x64']},{versions['x86']}")
