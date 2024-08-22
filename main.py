import discord
import telegram
import v2rayn
import wetype
from common import CLIENT


def main():
    exceptions = []
    for mod in (wetype, discord, v2rayn):
        try:
            mod.main()
        except Exception as e:
            exceptions.append(e)
    CLIENT.close()
    if exceptions:
        raise ExceptionGroup("Update failed", exceptions)


main()
