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
