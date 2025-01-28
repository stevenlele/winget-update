import re
from collections.abc import Sequence
from datetime import datetime
from difflib import unified_diff
from hashlib import sha256
from io import StringIO
from typing import Required, TypedDict

from pangu import spacing
from rich import print
from rich.syntax import Syntax
from ruamel.yaml import YAML, CommentedMap, CommentToken
from ruamel.yaml.scalarstring import LiteralScalarString

from common import CLIENT, UpdateArgs

type Manifests = dict[str, str]


class Installer(TypedDict, total=False):
    Architecture: str
    InstallerType: str
    Scope: str
    InstallerUrl: Required[str]
    InstallerSha256: str
    UpgradeBehavior: str
    InstallerLocale: str


def fill_in_release_notes(
    manifests: Manifests, identifier: str, args: UpdateArgs, *, force: bool = False
) -> bool:
    assert (notes := args.get("release_notes"))
    changed = False
    for locale, (_notes, url) in notes.items():
        if _fill_in_release_notes_by_locale(
            manifests, identifier, args, notes=_notes, locale=locale, url=url, force=force
        ):
            changed = True
    return changed


def _fill_in_release_notes_by_locale(
    manifests: Manifests,
    identifier: str,
    args: UpdateArgs,
    *,
    notes: str,
    locale: str,
    url: str,
    force: bool,
) -> bool:
    notes = notes.strip().replace("\r\n", "\n")
    notes = re.sub(r"\[([^\]]+?)\]\(\S+?\)", r"\1", notes)  # links
    notes = re.sub(r"(^|\n)#+ (.+?)\n+", r"\1\2\n", notes)  # headings
    notes = re.sub(r"(\*{2,})([^*`\n]+?)\1", r"\2", notes)  # italics/bold
    if owner_and_repo := args.get("owner_and_repo"):
        notes = re.sub(
            rf"https://github\.com/{owner_and_repo}/(?:issues|pull|discussions)/(\d+)",
            r"#\1",
            notes,
        )
        notes = re.sub(
            r"https://github\.com/([-\w]+)/([-\w]+)/(?:issues|pull|discussions)/(\d+)",
            r"\1/\2#\3",
            notes,
        )
        notes = re.sub(r"(?:https://github\.com/.+?/commit/)?[0-9a-z]{40}", "", notes)
    if locale == "zh-CN":
        notes = spacing(notes)
    notes = re.sub(r" +$", "", notes, flags=re.MULTILINE)

    manifest = manifests[f"{identifier}.locale.{locale}.yaml"]
    if args.get("is_url_important") or force:
        assert url
        if not (manifest := _insert_property(manifest, "ReleaseNotesUrl", url, force=force)):
            return False
        assert (manifest := _insert_property(manifest, "ReleaseNotes", notes, force=True))
    else:
        if not (manifest := _insert_property(manifest, "ReleaseNotes", notes, force=force)):
            return False
        if url:
            manifest = _insert_property(manifest, "ReleaseNotesUrl", url, force=force) or manifest
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
    args: UpdateArgs,
):
    original = manifests.copy()
    locales = args.get("release_notes", {}).keys()

    for filename, text in manifests.items():
        text, newline = _normalize_crlf(text)
        yaml = _get_yaml()
        doc: CommentedMap = yaml.load(text)

        if doc.ca.comment:
            top_comments: list[CommentToken] = doc.ca.comment[1]  # type: ignore
            assert len(top_comments) <= 2
            if len(top_comments) == 2:
                top_comments.pop(0)
            assert top_comments[0].value.startswith("# yaml-language-server")
            top_comments[0].value = top_comments[0].value.replace("1.6.0", "1.9.0")

        doc["ManifestVersion"] = doc["ManifestVersion"].replace("1.6.0", "1.9.0")
        doc["PackageVersion"] = version

        if filename.endswith(".installer.yaml"):
            inferred_date = None

            if args.get("override_old_installers"):
                doc["Installers"] = [
                    {**installer, "InstallerSha256": None} for installer in new_installers
                ]

            installers: list[Installer] = doc["Installers"]
            assert len(installers) == len(new_installers)

            hashes = {}

            for installer, new_installer in zip(installers, new_installers):
                _installer = {**installer}
                del _installer["InstallerUrl"], _installer["InstallerSha256"]
                _new_installer = {**new_installer}
                hashes[_new_installer.pop("InstallerUrl")] = None
                assert _installer.items() & _new_installer.items() == _new_installer.items()

            for url in hashes:
                print("Downloading", url)
                with CLIENT.stream("GET", url) as response:
                    assert response.is_success
                    last_modified = datetime.strptime(
                        response.headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z"
                    ).date()
                    if inferred_date is None:
                        inferred_date = last_modified
                    else:
                        inferred_date = min(last_modified, inferred_date)

                    h = sha256(usedforsecurity=False)
                    for chunk in response.iter_bytes():
                        h.update(chunk)
                hashes[url] = h.hexdigest().upper()

            for installer, new_installer in zip(installers, new_installers):
                installer["InstallerUrl"] = (url := new_installer["InstallerUrl"])
                installer["InstallerSha256"] = hashes[url]

            doc["ReleaseDate"] = args.get("release_date", inferred_date)
        elif ".locale." in filename:
            if (prefix := args.get("keep_notes_on_version_prefix")) and version.startswith(prefix):
                pass
            elif filename.removesuffix(".yaml").partition(".locale.")[2] in locales:
                pass
            else:
                doc.pop("ReleaseNotes", None)  # type: ignore
                doc.pop("ReleaseNotesUrl", None)  # type: ignore

        yaml.dump(doc, s := StringIO(newline=newline))
        manifests[filename] = s.getvalue()

    if locales:
        fill_in_release_notes(manifests, identifier, args, force=True)

    _print_manifests_diff(original, manifests)


def _print_manifests_diff(original: Manifests, manifests: Manifests) -> None:
    for filename in original:
        diff = "".join(
            unified_diff(
                original[filename].splitlines(True),
                manifests[filename].splitlines(True),
                f"{filename} (old)",
                f"{filename} (new)",
            )
        )
        print(Syntax(diff, "diff"))


def _normalize_crlf(text: str) -> tuple[str, str]:
    if "\r\n" not in text:
        return text, "\n"

    assert "\n" not in text.replace("\r\n", "")
    return text.replace("\r\n", "\n"), "\r\n"


def _insert_property(text: str, key: str, value: object, *, force: bool = False) -> str | None:
    text, newline = _normalize_crlf(text)
    text, placeholders = re.subn(rf"^# {key}:\s*$", f"{key}: 0", text, flags=re.MULTILINE)
    if placeholders > 1:
        raise RuntimeError("Illegal document")

    if isinstance(value, str) and "\n" in value:
        value = LiteralScalarString(value)

    yaml = _get_yaml()
    doc: CommentedMap = yaml.load(text)

    if placeholders:
        assert doc[key] == 0 and value
        doc[key] = value
    elif not value:
        if force:
            doc.pop(key, None)  # type: ignore
        else:
            return None
    elif key in doc:
        if force:
            doc[key] = value
        else:
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
            "ReleaseNotes",
            "ReleaseNotesUrl",
            "PurchaseUrl",
            "InstallationNotes",
            "Documentations",
            "ManifestType",
            "ManifestVersion",
        )
        local_index = properties.index(key)

        doc_indices = {k: i for i, k in enumerate(doc)}
        before = [i for p in properties[:local_index] if (i := doc_indices.get(p))]
        after = [i for p in properties[local_index + 1 :] if (i := doc_indices.get(p))]
        assert list(range(before[0], after[-1] + 1)) == before + after

        doc.insert(after[0], key, value)

    token: CommentToken
    if (
        isinstance(value, LiteralScalarString)
        and (post_comments := doc.ca.items.get(key))
        and (token := post_comments[2])
        and token.value.startswith("\n")
    ):
        token.value = token.value.lstrip()

    yaml.dump(doc, s := StringIO(newline=newline))
    return s.getvalue()


def _get_yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml
