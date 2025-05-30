from base64 import b64encode
from datetime import datetime
from os import getenv
from os.path import expandvars
from pprint import pformat
from time import sleep
from typing import Any, Callable, Literal, Sequence, TypedDict

from rich import print

from common import UpdateArgs, Version, retry_request, try_parse_version
from manifest import Installer, Manifests, fill_in_release_notes, update_new_version

assert (_TOKEN := getenv("GITHUB_TOKEN"))
HEADERS = {"Authorization": f"token {_TOKEN}"}

assert (OWNER := getenv("GITHUB_REPOSITORY_OWNER"))

MICROSOFT = "microsoft"
WINGET_PKGS = "winget-pkgs"
MICROSOFT_WINGET_PKGS = f"{MICROSOFT}/{WINGET_PKGS}"
DEFAULT_BRANCH = "master"


type PRNumber = int


def get_gh_api(url: str) -> Any:
    return _rest("GET", url)


def update(
    identifier: str,
    version: str,
    installers: Sequence[Installer],
    args: UpdateArgs = {"base_version": ""},
) -> PRNumber | None:
    print(f"Updating {identifier!r} to {version}", end="")
    if args.get("release_notes"):
        print(" with release notes...")
    else:
        print(" without release notes...")

    prs = _get_existing_prs(identifier, version)
    print(f"Found {len(prs)} existing PRs")

    owner_open_pr = None
    other_open_pr = None

    for i, pr in enumerate(prs):
        print(f"({i+1}) ", end="")
        _print_pr(pr)

        if pr["headRepositoryOwner"] == OWNER:
            if pr["state"] == "OPEN":
                assert owner_open_pr is None
                owner_open_pr = pr
            else:
                assert pr["headRef"] is None
        elif pr["state"] == "OPEN":
            if pr["author"] == "john-preston":
                print("Ignoring PR by john-preston")
                continue
            assert other_open_pr is None
            other_open_pr = pr

    if owner_open_pr:
        print("Checking owner's PR...")
        assert (ref := owner_open_pr["headRef"])
        sha = ref["sha"]
    elif other_open_pr:
        print(f"Checking PR by {other_open_pr['author']}...")
        assert (ref := other_open_pr["headRef"])
        sha = ref["sha"]
    else:
        print(f"Checking {DEFAULT_BRANCH} branch...")
        refs = _rest(
            "GET", f"/repos/{MICROSOFT_WINGET_PKGS}/git/matching-refs/heads/{DEFAULT_BRANCH}"
        )
        assert len(refs) == 1
        sha = refs[0]["object"]["sha"]

    path = _get_path(identifier, version)
    message_prefix = "ReleaseNotes"
    if not (manifests := _get_manifests(sha, path)):
        assert refs
        print("There's no manifest of this version, performing update...")
        manifests = _get_base_manifests(identifier, args, sha=sha)
        update_new_version(manifests, identifier, version, installers, args)
        message_prefix = "New version"
    elif owner_open_pr and (base_version := args.get("base_version")) and version != base_version:
        print("Repo info is rolled back, rerunning update...")
        manifests = _get_base_manifests(identifier, args, sha=sha)
        update_new_version(manifests, identifier, version, installers, args)
        message_prefix = "New version (rerun)"
    elif not args.get("release_notes") or not fill_in_release_notes(manifests, identifier, args):
        print("This branch is up-to-date, we'll mark this update as done")
        return None
    elif other_open_pr and not owner_open_pr:
        print("We need to wait until this PR gets merged")
        return other_open_pr["number"]

    del other_open_pr

    message = f"{message_prefix}: {identifier} version {version}"
    if owner_open_pr:
        _create_commit(ref["name"], message, path, manifests, sha)
        print("[green]✓ Updated existing pull request[/]")
        return None

    create_fork()
    branch_name = f"{identifier}-{version}--{datetime.now():%Y%m%d-%H%M%S}"
    print(f"Creating new branch {branch_name!r}...")
    _create_branch(branch_name, sha)
    commit_url = _create_commit(branch_name, message, path, manifests, sha)
    print(f"Created commit: {commit_url}")
    pr_url = _create_pr(message, branch_name)
    print(f"Created PR: {pr_url}")
    return None


def _rest(method: str, url: str, *, json: dict | None = None) -> Any:
    if url.startswith("/"):
        url = f"https://api.github.com{url}"
    else:
        assert url.startswith("https://api.github.com")
    response = retry_request(method, url, json=json, headers=HEADERS)
    if response.status_code == 204:
        assert not response.content
        return None
    payload = response.json()
    if not response.is_success:
        raise RuntimeError(pformat(payload, sort_dicts=False))
    return payload


def is_pr_open(number: int) -> bool:
    response = _rest("GET", f"/repos/{MICROSOFT_WINGET_PKGS}/issues/{number}")
    return response["state"] == "open"


def _graphql(query: str, variables: dict = {}, accept_error: Callable[[list], bool] | None = None):
    response = retry_request(
        "POST",
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=HEADERS,
    )
    assert response.is_success, response.text
    payload = response.json()
    if (errors := payload.get("errors")) and (accept_error is None or not accept_error(errors)):
        raise RuntimeError(pformat(errors, sort_dicts=False))
    return payload["data"]


class _Ref(TypedDict):
    name: str
    # target: GitObject
    sha: str


class _PullRequest(TypedDict):
    number: int
    title: str
    state: Literal["OPEN", "CLOSED", "MERGED"]
    url: str
    headRef: _Ref | None
    headRepositoryOwner: str  # User
    author: str  # User


def _print_pr(pr: _PullRequest):
    print(repr(pr["title"]), end="")
    if author := pr.get("author"):
        print(f" by {author}", end="")
    print(f" ({pr['state']})")
    print(pr["url"])


def _get_existing_prs(identifier: str, version: str) -> list[_PullRequest]:
    result = _graphql(
        """query PullRequestSearch($q: String!) { search(query: $q, type: ISSUE, first: 30) {"""
        """nodes { ... on PullRequest {"""
        """number title state url headRef { name target { oid } } headRepositoryOwner { login } author { login }"""
        """} } } }""",
        {"q": f"repo:{MICROSOFT_WINGET_PKGS} type:pr in:title {identifier} {version}"},
    )["search"]["nodes"]
    for pr in result:
        pr["headRepositoryOwner"] = pr["headRepositoryOwner"]["login"]
        pr["author"] = pr["author"]["login"]
        if headRef := pr.get("headRef"):
            headRef["sha"] = headRef.pop("target")["oid"]
    return result


def _create_branch(name: str, sha: str):
    payload = {"ref": f"refs/heads/{name}", "sha": sha}
    _rest("POST", f"/repos/{OWNER}/{WINGET_PKGS}/git/refs", json=payload)
    global _should_delete_fork
    _should_delete_fork = False


def create_fork() -> None:
    global _owner_repo_id, _should_delete_fork
    _should_delete_fork = False
    if _owner_repo_id:
        return
    print("Creating fork...")
    _owner_repo_id = _rest(
        "POST", f"/repos/{MICROSOFT_WINGET_PKGS}/forks", json={"default_branch_only": True}
    )["node_id"]
    _rest(
        "PATCH",
        f"/repos/{OWNER}/{WINGET_PKGS}",
        json={"has_issues": False, "has_wiki": False, "has_projects": False},
    )
    _rest(
        "PUT",
        f"/repos/{OWNER}/{WINGET_PKGS}/actions/permissions",
        json={"enabled": False},
    )
    print("Sleeping 5 seconds to let the fork settle...")
    sleep(5)


def delete_fork_if_should():
    if not _owner_repo_id or not _should_delete_fork:
        return
    print("Deleting fork...")
    _rest("DELETE", f"/repos/{OWNER}/{WINGET_PKGS}")


def _get_directory(sha: str, path: str) -> dict:
    response = _graphql(
        """query GetDirectoryContentWithText($owner: String!, $name: String!, $expression: String!) {"""
        """repository(owner: $owner, name: $name) { object(expression: $expression) { ... on Tree {"""
        """entries { name object { ... on Blob { text } } } } } } }""",
        {
            "owner": MICROSOFT,
            "name": WINGET_PKGS,
            "expression": f"{sha}:{path}",
        },
    )
    return response


def _get_manifests(sha: str, path: str) -> Manifests:
    response = _get_directory(sha, path)
    if response["repository"]["object"] is None:
        return {}
    return {
        entry["name"]: entry["object"]["text"]
        for entry in response["repository"]["object"]["entries"]
    }


def _get_subdirectories(sha: str, path: str) -> list[str]:
    response = _get_directory(sha, path)
    return [
        entry["name"]
        for entry in response["repository"]["object"]["entries"]
        if not entry["object"]
    ]


def _get_path(identifier: str, version: str | None = None) -> str:
    base = f"manifests/{identifier[0].lower()}/{identifier.replace('.', '/')}"
    return base if version is None else f"{base}/{version}"


def _get_base_manifests(identifier: str, args: UpdateArgs, *, sha: str) -> Manifests:
    if (base_version := args.get("base_version")) and (
        manifests := _get_manifests(sha, _get_path(identifier, base_version))
    ):
        return manifests

    raw_versions = _get_subdirectories(sha, _get_path(identifier))
    if base_version:
        base_version = Version(base_version)
        version = max(
            version
            for raw_version in raw_versions
            if (version := try_parse_version(raw_version)) and version <= base_version
        )
    else:
        version = max(
            version for raw_version in raw_versions if (version := try_parse_version(raw_version))
        )

    assert (manifests := _get_manifests(sha, _get_path(identifier, f"{version}")))
    return manifests


def _base64_encode(text: str) -> str:
    return b64encode(text.encode()).decode()


def _create_commit(
    branch_name: str,
    commit_message: str,
    path: str,
    manifests: Manifests,
    head_sha: str,
) -> str:
    response = _graphql(
        """mutation CreateCommit($input: CreateCommitOnBranchInput!) {"""
        """createCommitOnBranch(input: $input) { commit { url } } }""",
        {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": f"{OWNER}/{WINGET_PKGS}",
                    "branchName": branch_name,
                    # id: str
                },
                "message": {"headline": commit_message},
                "fileChanges": {
                    "additions": [
                        {"path": f"{path}/{filename}", "contents": _base64_encode(content)}
                        for filename, content in manifests.items()
                    ]
                },
                "expectedHeadOid": head_sha,
            }
        },
    )
    return response["createCommitOnBranch"]["commit"]["url"]


_owner_repo_id: str | None = None
_should_delete_fork = True


def check_repo_and_delete_merged_branches():
    repository = _graphql(
        """query GetBranches($owner: String!, $name: String!) { repository(name: $name, owner: $owner) {"""
        """id isEmpty defaultBranchRef { name } refs(first: 100, refPrefix: "refs/heads/") { nodes { name """
        """associatedPullRequests(first: 5) { nodes { title url state repository { nameWithOwner } } }"""
        """} } } }""",
        {"owner": OWNER, "name": WINGET_PKGS},
        lambda errors: len(errors) == 1
        and (error := errors[0])["type"] == "NOT_FOUND"
        and error["path"] == ["repository"],
    )["repository"]
    if repository is None:
        print("Fork does not exist")
        return
    global _owner_repo_id
    _owner_repo_id = repository["id"]

    if repository["isEmpty"]:
        """This repository is temporarily unavailable.

        The backend storage is temporarily offline.
        Usually this means the storage server is undergoing maintenance.
        Please contact support if the problem persists.
        """
        assert repository["defaultBranchRef"] is None
        print("Fork is broken, deleting it...")
        delete_fork_if_should()
        _owner_repo_id = None
        return

    print("Checking for merged branches...")
    default_branch_name = repository["defaultBranchRef"]["name"]
    branch_names_pending_deletion = []
    for ref in repository["refs"]["nodes"]:
        prs = ref["associatedPullRequests"]["nodes"]
        if ref["name"] == default_branch_name:
            assert not prs
            continue
        print(f"Branch {ref['name']!r}:")
        if not prs:
            print("[bold red]! There are no PRs associated with this branch[/]")
            global _should_delete_fork
            _should_delete_fork = False
            continue
        can_delete_branch = True
        for pr in prs:
            _print_pr(pr)
            if pr["repository"]["nameWithOwner"] != MICROSOFT_WINGET_PKGS:
                print("[bold red]! This PR is not against the official repo[/]")
                can_delete_branch = False
            elif pr["state"] == "CLOSED":
                print("[bold red]! This PR is closed unmerged[/]")
                can_delete_branch = False
            elif pr["state"] == "OPEN":
                can_delete_branch = False
            else:
                assert pr["state"] == "MERGED"
        if can_delete_branch:
            print("[green]✓ This branch will be deleted[/]")
            branch_names_pending_deletion.append(ref["name"])
        else:
            print("This branch will not be deleted")
            _should_delete_fork = False
    if branch_names_pending_deletion:
        print("Deleting branches:", branch_names_pending_deletion)
        _graphql(
            """mutation UpdateRefs($input: UpdateRefsInput!) { updateRefs(input: $input) { clientMutationId } }""",
            {
                "input": {
                    "repositoryId": _owner_repo_id,
                    "refUpdates": [
                        {
                            "name": f"refs/heads/{branch_name}",
                            "afterOid": "0" * 40,
                        }
                        for branch_name in branch_names_pending_deletion
                    ],
                }
            },
        )


def _create_pr(title: str, branch_name: str) -> str:
    return _rest(
        "POST",
        f"/repos/{MICROSOFT_WINGET_PKGS}/pulls",
        json={
            "title": title,
            "head": f"{OWNER}:{branch_name}",
            "body": "Created in " + expandvars(
                "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
            ),
            "base": DEFAULT_BRANCH,
        },
    )["html_url"]
