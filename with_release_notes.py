import json
from abc import ABC, abstractmethod
from typing import TypedDict, final

from rich import print

from common import UpdateArgs, Version
from github import PRNumber, update
from manifest import Installer


class _VersionData(TypedDict):
    version: str
    has_release_notes: bool
    blocking_pr: PRNumber | None


class WithReleaseNotes(ABC):
    version: str

    def __init__(self, moniker: str, identifier: str) -> None:
        self.moniker = moniker
        self.identifier = identifier

    @final
    def main(self):
        with open(storage := f"{self.moniker}.json") as f:
            old_version_data: _VersionData = json.load(f)

        if old_blocking_pr := old_version_data["blocking_pr"]:
            print(f"[bold red]{self.moniker}: Last update was blocked by PR #{old_blocking_pr}[/]")

        old_version = Version(old_version_data["version"])
        assert (latest_version := self.get_latest_version()) >= old_version
        if (
            old_version == latest_version
            and old_version_data["has_release_notes"]
            and not old_blocking_pr
        ):
            return

        self.version = (version := f"{latest_version}")
        has_release_notes = self.has_release_notes()
        if latest_version == old_version and not has_release_notes:
            return

        blocking_pr = update(
            self.identifier, version, self.get_installers(), self.get_update_args()
        )

        with open(storage, "w") as f:
            new_version_data: _VersionData = {
                "version": version,
                "has_release_notes": has_release_notes,
                "blocking_pr": blocking_pr,
            }
            json.dump(new_version_data, f, separators=(",", ":"))

    @abstractmethod
    def get_latest_version(self) -> Version: ...

    @abstractmethod
    def has_release_notes(self) -> bool: ...

    @abstractmethod
    def get_installers(self) -> list[Installer]: ...

    @abstractmethod
    def get_update_args(self) -> UpdateArgs: ...
