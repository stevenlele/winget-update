import rich

import discord
import github
import telegram
import v2rayn
import wetype
from common import CLIENT


def main():
    rich.reconfigure(force_terminal=True, width=4096)
    exceptions = []
    github.check_repo_and_delete_merged_branches()
    for mod in (wetype, discord, v2rayn):
        try:
            mod.main()
        except Exception as e:
            exceptions.append(e)
    if not exceptions:
        github.delete_fork_if_should()
    CLIENT.close()
    if exceptions:
        raise ExceptionGroup("Update failed", exceptions)


main()
