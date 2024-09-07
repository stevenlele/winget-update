import re
from collections.abc import Sequence
from datetime import datetime
from hashlib import sha256
from io import StringIO
from typing import TypedDict

from pangu import spacing
from rich import print
from ruamel.yaml import YAML, CommentedMap, CommentToken
from ruamel.yaml.scalarstring import LiteralScalarString

from common import CLIENT, KomacArgs

type Manifests = dict[str, str]


class Installer(TypedDict, total=False):
    Architecture: str
    InstallerType: str
    Scope: str
    InstallerUrl: str
    InstallerSha256: str
    UpgradeBehavior: str


def fill_in_release_notes(manifests: Manifests, identifier: str, args: KomacArgs) -> bool:
    assert (notes := args.get("release_notes"))
    assert (locale := args.get("release_notes_locale"))

    notes = notes.strip().replace("\r\n", "\n")
    if (owner := args.get("owner")) and (repo := args.get("repo")):
        notes = re.sub(
            rf"https://github\.com/{owner}/{repo}/(?:issues|pull|discussions)/(\d+)", r"#\1", notes
        )
        notes = re.sub(
            r"https://github\.com/([-\w]+)/([-\w]+)/(?:issues|pull|discussions)/(\d+)",
            r"\1/\2#\3",
            notes,
        )
        notes = re.sub(r"(?:https://github\.com/.+?/commit/)?[0-9a-z]{40}", "", notes)
    notes = spacing(notes)
    notes = re.sub(r" +$", "", notes, flags=re.MULTILINE)

    if not notes:
        return False

    manifest = manifests[f"{identifier}.locale.{locale}.yaml"]
    manifest = _insert_property(manifest, "ReleaseNotes", notes)
    if not manifest:
        return False
    if url := args.get("release_notes_url"):
        manifest = _insert_property(manifest, "ReleaseNotesUrl", url) or manifest
    manifests[f"{identifier}.locale.{locale}.yaml"] = manifest

    if date := args.get("release_date"):
        manifest = manifests[f"{identifier}.installer.yaml"]
        if manifest := _insert_property(manifest, "ReleaseDate", date):
            manifests[f"{identifier}.installer.yaml"] = manifest

    return True


def update_new_version(
    manifests: Manifests,
    identifier: str,
    version: str,
    new_installers: Sequence[Installer],
    args: KomacArgs,
):
    for filename, text in manifests.items():
        text, newline = _normalize_crlf(text)
        yaml = YAML()
        doc: CommentedMap = yaml.load(text)

        top_comments: list[CommentToken] = doc.ca.comment[1]  # type: ignore
        assert len(top_comments) <= 2
        if len(top_comments) == 2:
            top_comments.pop(0)
        assert top_comments[0].value.startswith("# yaml-language-server")

        doc["PackageVersion"] = version

        if filename.endswith(".installer.yaml"):
            inferred_date = None

            installers: list[Installer] = doc["Installers"]
            assert len(installers) == len(new_installers)

            hashes = {}

            for installer, new_installer in zip(installers, new_installers):
                installer = installer.copy()
                del installer["InstallerUrl"], installer["InstallerSha256"]
                new_installer = new_installer.copy()
                hashes[new_installer.pop("InstallerUrl")] = None
                assert installer.items() & new_installer.items() == new_installer.items()

            for url in hashes:
                print("Downloading", url)
                with CLIENT.stream("GET", url) as response:
                    assert response.is_success
                    last_modified = datetime.strptime(
                        response.headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z"
                    ).strftime("%Y-%m-%d")
                    if inferred_date is None:
                        inferred_date = last_modified
                    else:
                        assert inferred_date == last_modified

                    h = sha256(usedforsecurity=False)
                    for chunk in response.iter_bytes():
                        h.update(chunk)
                hashes[url] = h.hexdigest().upper()

            for installer, new_installer in zip(installers, new_installers):
                assert (url := new_installer.get("InstallerUrl"))
                installer["InstallerUrl"] = url
                installer["InstallerSha256"] = hashes[url]

            doc["ReleaseDate"] = args.get("release_date", inferred_date)
        elif (locale := args.get("release_notes_locale")) and filename.endswith(
            f".locale.{locale}.yaml"
        ):
            if (prefix := args.get("keep_notes_on_version_prefix")) and version.startswith(prefix):
                pass
            else:
                doc.pop("ReleaseNotes", None)  # type: ignore
                doc.pop("ReleaseNotesUrl", None)  # type: ignore

        yaml.dump(doc, s := StringIO(newline=newline))
        manifests[filename] = s.getvalue()

    if args.get("release_notes"):
        fill_in_release_notes(manifests, identifier, args)


def _normalize_crlf(text: str) -> tuple[str, str]:
    if "\r\n" not in text:
        return text, "\n"

    assert "\n" not in text.replace("\r\n", "")
    return text.replace("\r\n", "\n"), "\r\n"


def _insert_property(text: str, key: str, value: str) -> str | None:
    text, newline = _normalize_crlf(text)
    text, placeholders = re.subn(rf"^# {key}:\s*$", f"{key}: 0", text, flags=re.MULTILINE)
    if placeholders > 1:
        raise RuntimeError("Illegal document")

    if "\n" in value:
        value = LiteralScalarString(value)

    yaml = YAML()
    doc: CommentedMap = yaml.load(text)

    if placeholders:
        assert doc[key] == 0
        doc[key] = value
    elif key in doc:
        return None
    elif key == "ReleaseDate":
        doc[key] = value
    else:
        assert key in {"ReleaseNotes", "ReleaseNotesUrl"}
        properties = (
            "ShortDescription",
            "Description",
            "Moniker",
            "Tags",
            "Agreements",
            "Documentations",
            "ReleaseNotes",
            "ReleaseNotesUrl",
            "PurchaseUrl",
            "InstallationNotes",
            "ManifestType",
            "ManifestVersion",
        )
        local_index = properties.index(key)

        doc_indices = {k: i for i, k in enumerate(doc)}
        before = [i for p in properties[:local_index] if (i := doc_indices.get(p))]
        after = [i for p in properties[local_index + 1 :] if (i := doc_indices.get(p))]
        assert list(range(before[0], after[-1] + 1)) == before + after

        doc.insert(after[0], key, value)

    yaml.dump(doc, s := StringIO(newline=newline))
    return s.getvalue()
