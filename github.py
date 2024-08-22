from os import getenv
from pprint import pformat
from typing import Any, Literal, Sequence, TypedDict

from rich import print
from ruamel.yaml import YAML

from common import CLIENT, KomacArgs

assert (_TOKEN := getenv("GITHUB_TOKEN"))
HEADERS = {"Authorization": f"token {_TOKEN}"}

assert (OWNER := getenv("GITHUB_REPOSITORY_OWNER"))

MICROSOFT = "microsoft"
WINGET_PKGS = "winget-pkgs"


class Installer(TypedDict, total=False):
    Architecture: str
    InstallerType: str
    Scope: str
    InstallerUrl: str
    UpgradeBehavior: str


type PRToWait = int
type Manifests = dict[str, str]


def update(
    identifier: str,
    version: str,
    urls: Sequence[Installer],
    args: KomacArgs = {},
) -> PRToWait | None:
    print(f"Updating {identifier!r} to {version}", end="")
    if "release_notes" in args:
        print(" with release notes...")
    else:
        print(" without release notes...")

    prs = get_existing_prs(identifier, version)
    print(f"Found {len(prs)} existing PRs")

    owner_open_pr = None
    other_open_pr = None

    for i, pr in enumerate(prs):
        print(f"({i+1}) ", end="")
        print_pr(pr)

        if pr["headRepositoryOwner"]["login"] == OWNER:
            if pr["state"] == "OPEN":
                assert owner_open_pr is None
                owner_open_pr = pr
            elif head_ref := pr["headRef"]:
                assert pr["state"] == "MERGED"
                print("- Deleting merged branch...")
                delete_branch(head_ref["name"])
        elif pr["state"] == "OPEN":
            assert other_open_pr is None
            other_open_pr = pr

    if owner_open_pr:
        print("Checking owner's PR...")
        assert (ref := owner_open_pr["headRef"])
    elif other_open_pr:
        print(f"Checking PR by {other_open_pr['author']['login']}...")
        assert (ref := other_open_pr["headRef"])
    else:
        print("Checking master branch...")
        ref = None

    manifests = get_manifests(ref, identifier, version)

    if check_manifests(manifests, urls, args):
        print("This branch is up-to-date, we'll mark this update as done")
        return None
    elif other_open_pr:
        print("We need to wait until this PR gets merged")
        return other_open_pr["number"]

    del other_open_pr

    # create branch or use existing branch
    # from scratch or add release notes
    # create pull request or skip


def rest(method: str, url: str, *, json: dict | None = None) -> Any:
    if url.startswith("/"):
        url = f"https://api.github.com{url}"
    else:
        assert url.startswith("https://api.github.com")
    response = CLIENT.request(method, url, json=json, headers=HEADERS)
    if response.status_code == 204:
        assert not response.content
        return None
    payload = response.json()
    if not response.is_success:
        raise RuntimeError(pformat(payload, sort_dicts=False))
    return payload


def is_pr_open(number: int) -> bool:
    response = rest("GET", f"/repos/{MICROSOFT}/{WINGET_PKGS}/issues/{number}")
    return response["state"] == "open"


def graphql(query: str, variables: dict = {}):
    response = CLIENT.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=HEADERS,
    )
    assert response.is_success
    payload = response.json()
    if errors := payload.get("errors"):
        raise RuntimeError(pformat(errors, sort_dicts=False))
    return payload["data"]


class GitObject(TypedDict):
    oid: str


class Ref(TypedDict):
    name: str
    target: GitObject


class User(TypedDict):
    login: str


class PullRequest(TypedDict):
    number: int
    title: str
    state: Literal["OPEN", "CLOSED", "MERGED"]
    url: str
    headRef: Ref | None
    headRepositoryOwner: User
    author: User


def print_pr(pr: PullRequest):
    print(f"{pr['title']!r} by {pr['author']['login']} ({pr['state']})")
    print(pr["url"])


def get_existing_prs(identifier: str, version: str) -> list[PullRequest]:
    return graphql(
        """query PullRequestSearch($q: String!) { search(query: $q, type: ISSUE, first: 30) {"""
        """nodes { ... on PullRequest {"""
        """number title state url headRef { name target { oid } } headRepositoryOwner { login } author { login }"""
        """} } } }""",
        {"q": f"repo:{MICROSOFT}/{WINGET_PKGS} type:pr in:title {identifier} {version}"},
    )["search"]["nodes"]


def create_branch(name: str, sha: str):
    payload = {"ref": f"refs/heads/{name}", "sha": sha}
    rest("POST", f"/repos/{OWNER}/{WINGET_PKGS}/git/refs", json=payload)


def delete_branch(name: str):
    rest("DELETE", f"/repos/{OWNER}/{WINGET_PKGS}/git/refs/heads/{name}")


def create_fork():
    rest("POST", f"/repos/{MICROSOFT}/{WINGET_PKGS}/forks", json={"default_branch_only": True})


def delete_fork():
    rest("DELETE", f"/repos/{OWNER}/{WINGET_PKGS}")


def get_manifests(sha: str, identifier: str, version: str) -> Manifests:
    response = graphql(
        """query GetDirectoryContentWithText($owner: String!, $name: String!, $expression: String!) {"""
        """repository(owner: $owner, name: $name) { object(expression: $expression) { ... on Tree {"""
        """entries { name object { ... on Blob { text } } } } } } }""",
        {
            "owner": MICROSOFT,
            "name": WINGET_PKGS,
            "expression": f"{sha}:{get_path(identifier, version)}",
        },
    )
    return {
        entry["name"]: entry["object"]["text"]
        for entry in response["repository"]["object"]["entries"]
    }


def get_path(identifier: str, version: str) -> str:
    return f"manifests/{identifier[0].lower()}/{identifier.replace('.', '/')}/{version}"


def check_manifests(manifests: Manifests, urls: Sequence[Installer], args: KomacArgs) -> bool:
    if not manifests:
        print("There's no manifest of this version")
        return False
    raise NotImplementedError
