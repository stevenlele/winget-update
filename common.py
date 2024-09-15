import re
import subprocess
from datetime import date
from sys import stderr, stdout
from typing import Required, Sequence, TypedDict

import httpx

CLIENT = httpx.Client(follow_redirects=True)


def get(url: str):
    assert (response := CLIENT.get(url)).is_success
    return response.text


class UpdateArgs(TypedDict, total=False):
    base_version: Required[str]
    release_date: date
    release_notes: str
    release_notes_locale: str
    release_notes_url: str
    owner_and_repo: str
    keep_notes_on_version_prefix: str
    is_url_important: bool
    override_old_installers: bool


def run_komac(identifier: str, version: str, urls: str | Sequence[str]):
    command = ["./komac", "update", identifier, "-v", version, "--submit", "-u"]
    if isinstance(urls, str):
        command.append(urls)
    else:
        command.extend(urls)
    print("$", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True, stdout=stdout, stderr=stderr)


VERSION_REGEX = re.compile(r"\d+(?:\.\d+)+")


class Version:
    SEP = re.compile(r"[.r]")

    def __init__(self, arg: str | tuple[int, ...]) -> None:
        if isinstance(arg, str):
            self.version = arg
            self.value = tuple(map(int, self.SEP.split(arg)))
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


def try_parse_version(version: str) -> Version | None:
    try:
        return Version(version)
    except ValueError:
        return None
