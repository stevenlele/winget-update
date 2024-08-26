import re
import subprocess
from base64 import b64encode
from os import getenv
from sys import stderr, stdout
from typing import Sequence, TypedDict

import httpx

CLIENT = httpx.Client()


def get(url: str):
    assert (response := CLIENT.get(url)).is_success
    return response.text


def get_gh_api(url: str):
    assert (token := getenv("GITHUB_TOKEN"))
    assert (response := CLIENT.get(url, headers={"Authorization": f"token {token}"})).is_success
    return response.json()


class KomacArgs(TypedDict, total=False):
    base_version: str
    release_date: str
    release_notes: str
    release_notes_locale: str
    release_notes_url: str
    owner: str
    repo: str


def run_komac(identifier: str, version: str, urls: str | Sequence[str], args: KomacArgs = {}):
    command = ["./komac", "update", identifier, "-v", version, "--submit", "-u"]
    if isinstance(urls, str):
        command.append(urls)
    else:
        command.extend(urls)
    for key, value in args.items():
        command.append(f"--{key.replace('_', '-')}")
        command.append(f"-- {value}" if (value := str(value)).startswith("-") else value)
    print("$", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True, stdout=stdout, stderr=stderr)


def base64_encode(text: str) -> str:
    return b64encode(text.encode()).decode()


VERSION_REGEX = re.compile(r"\d+(?:\.\d+)+")


class VersionData(TypedDict):
    version: str
    has_release_notes: bool


class Version:
    def __init__(self, arg: str | tuple[int, ...]) -> None:
        if isinstance(arg, str):
            self.version = arg
            self.value = tuple(map(int, arg.split(".")))
        else:
            self.version = ".".join(map(str, arg))
            self.value = arg

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
