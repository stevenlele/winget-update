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
    memo: object


class WithReleaseNotes(ABC):
    version: str
    old_version: str

    def __init__(self, moniker: str, identifier: str) -> None:
        self.moniker = moniker
        self.identifier = identifier

    @final
    def main(self):
        with open(storage := f"{self.moniker}.json") as f:
            old_version_data: _VersionData = json.load(f)

        self.memo = old_version_data["memo"]

        if old_blocking_pr := old_version_data["blocking_pr"]:
            print(f"[bold red]{self.moniker}: Last update was blocked by PR #{old_blocking_pr}[/]")

        self.old_version = old_version_data["version"]
        old_version = Version(self.old_version)
        if (latest_version := self.get_latest_version()) < old_version:
            return print(
                f"::error file={self.moniker}.py,title=Version"
                f" rollback::{self.moniker} {old_version} -> {latest_version}"
            )

        self.version = (version := f"{latest_version}")
        has_release_notes = self.has_release_notes()
        should_force_rerun = self.should_force_rerun()

        if old_version == latest_version:
            has_minor_update = False
            if not old_version_data["has_release_notes"] and has_release_notes:
                has_minor_update = True
            elif should_force_rerun:
                has_minor_update = True
            elif old_blocking_pr:
                has_minor_update = True
            if not has_minor_update:
                return

        args = self.get_update_args()
        args["should_force_rerun"] = should_force_rerun
        blocking_pr = update(self.identifier, version, self.get_installers(), args)

        with open(storage, "w") as f:
            new_version_data: _VersionData = {
                "version": version,
                "has_release_notes": has_release_notes,
                "blocking_pr": blocking_pr,
                "memo": self.memo,
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

    @abstractmethod
    def should_force_rerun(self) -> bool: ...
