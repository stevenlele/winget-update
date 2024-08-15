import json

from common import *


def main():
    with open("postman.txt") as f:
        old_version = Version(f.read())

    assert (version_1 := get_version_1(old_version)) >= old_version
    assert (version_2 := get_version_2(old_version)) >= old_version

    if version_1 > version_2:
        run_komac(
            "Postman.Postman",
            f"{version_1}",
            f"https://dl.pstmn.io/download/version/${version_1}/win64",
        )

    with open("postman.txt", "w") as f:
        f.write(str(max(version_1, version_2)))


def get_version_1(old_version: Version) -> Version:
    if not (response := get(f"https://dl.pstmn.io/update/WIN64/{old_version}/stable")):
        return old_version
    url = json.loads(response).split(" ")[1]
    assert url.startswith("https://dl.pstmn.io/download/") and url.endswith("-full.nupkg")
    assert (match := VERSION_REGEX.search(url))
    return Version(match.group())


def get_version_2(old_version: Version) -> Version:
    url = f"https://dl.pstmn.io/update/status?currentVersion={old_version}&platform=win64&channel=stable&arch=64"
    if not (response := get(url)):
        return old_version
    return Version(json.loads(response)["version"])
