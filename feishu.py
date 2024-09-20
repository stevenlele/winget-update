import json
from os import getenv
from typing import Any

import rich

from github import update


def _get_config(lang: str) -> dict[str, Any]:
    assert (config := getenv(lang))
    return json.loads(config)


def main():
    rich.reconfigure(force_terminal=True, width=4096)

    zh = _get_config("zh")
    en = _get_config("en")

    assert (version := zh["version"]) == en["version"]
    assert (url := zh["downloadUrl"]) == en["downloadUrl"]
    assert zh["downloadMd5"] == en["downloadMd5"]

    assert url.endswith(".zip")
    url = url[:-4] + ".exe"

    update(
        "ByteDance.Feishu",
        version,
        [{"InstallerUrl": url}],
        {
            "base_version": getenv("base_version", ""),
            "release_notes": {
                "zh-CN": (
                    zh["releaseNotes"],
                    "https://www.feishu.cn/hc/zh-CN/articles/360043073734",
                ),
                "en-US": (
                    en["releaseNotes"],
                    "https://www.feishu.cn/hc/en-US/articles/360043073734",
                ),
            },
        },
    )


if __name__ == "__main__":
    main()
