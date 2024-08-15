import re
import subprocess
from sys import stderr, stdout


def get(url: str):
    return subprocess.run(
        ("curl", url), check=True, stdout=subprocess.PIPE, stderr=stderr
    ).stdout.decode()


def run_komac(identifier: str, version: str, url: str, base_version: str = ""):
    command = ["./komac", "update", identifier, "-v", version, "-u", url, "--submit"]
    if base_version:
        command.extend(("--base-version", base_version))
    print("$", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True, stdout=stdout, stderr=stderr)


VERSION_REGEX = re.compile(r"\d+(?:\.\d+)+")


class Version:
    def __init__(self, version: str) -> None:
        self.version = version
        self.value = tuple(map(int, version.split(".")))

    def __eq__(self, other) -> bool:
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __lt__(self, other) -> bool:
        return self.value < other.value

    def __le__(self, other) -> bool:
        return self.value <= other.value

    def __gt__(self, other) -> bool:
        return self.value > other.value

    def __ge__(self, other) -> bool:
        return self.value >= other.value

    def __str__(self) -> str:
        return self.version

    def __repr__(self) -> str:
        return self.version
