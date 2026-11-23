import json
import socket
import struct
from contextlib import contextmanager
from datetime import date
from hashlib import md5, sha256
from tempfile import TemporaryFile
from typing import override

from common import CLIENT, UpdateArgs, Version, get
from manifest import Installer, sha256_cache
from with_release_notes import WithReleaseNotes


def main():
    QQ().main()


@contextmanager
def _download_signed(url: str):
    signed_url = CLIENT.post(
        "https://im.qq.com/http2rpc/gotrpc/noauth/trpc.qqntv2.urlsign.UrlSign/GetSign",
        headers={
            "x-oidb": '{"uint32_command":"0x9b8e","uint32_service_type":1}',
            "Referer": "https://im.qq.com/index/",
        },
        json={"url": url},
    ).raise_for_status().json()["data"]["url"]
    with CLIENT.stream("GET", signed_url, headers={"Referer": "https://im.qq.com/index/"}) as response:
        response.raise_for_status()
        yield response


def _get_exe_version(installer) -> Version:
    installer.seek(60)
    pe_offset = struct.unpack("<I", installer.read(4))[0]
    installer.seek(pe_offset)
    header = installer.read(24)
    assert header[:4] == b"PE\0\0"
    section_count = struct.unpack_from("<H", header, 6)[0]
    optional_size = struct.unpack_from("<H", header, 20)[0]
    optional = installer.read(optional_size)
    magic = struct.unpack_from("<H", optional)[0]
    directory_offset = 112 if magic == 0x20B else 96
    resource_rva, resource_size = struct.unpack_from("<II", optional, directory_offset + 16)
    sections = [installer.read(40) for _ in range(section_count)]
    section = next(
        section for section in sections
        if (rva := struct.unpack_from("<I", section, 12)[0]) <= resource_rva
        < rva + max(struct.unpack_from("<I", section, 8)[0], struct.unpack_from("<I", section, 16)[0])
    )
    resource_offset = struct.unpack_from("<I", section, 20)[0] + resource_rva - rva
    installer.seek(resource_offset)
    resources = installer.read(resource_size)
    count = sum(struct.unpack_from("<HH", resources, 12))
    version_entry = next(
        struct.unpack_from("<I", resources, offset + 4)[0]
        for offset in range(16, 16 + count * 8, 8)
        if struct.unpack_from("<I", resources, offset)[0] == 16
    )
    directory = version_entry & 0x7FFFFFFF
    directory = struct.unpack_from("<I", resources, directory + 20)[0] & 0x7FFFFFFF
    entry = struct.unpack_from("<I", resources, directory + 20)[0] & 0x7FFFFFFF
    version_rva, version_size = struct.unpack_from("<II", resources, entry)
    installer.seek(resource_offset + version_rva - resource_rva)
    version_info = installer.read(version_size)
    offset = version_info.index("VS_VERSION_INFO".encode("utf-16le"))
    offset = (offset + len("VS_VERSION_INFO".encode("utf-16le")) + 5) & ~3
    signature, _, version_ms, version_ls = struct.unpack_from("<4I", version_info, offset)
    assert signature == 0xFEEF04BD
    return Version((version_ms >> 16, version_ms & 0xFFFF, version_ls >> 16, version_ls & 0xFFFF))


class QQ(WithReleaseNotes):
    def __init__(self) -> None:
        super().__init__(__name__, "Tencent.QQ.NT")

    @override
    def get_latest_version(self) -> Version:
        self.config = json.loads(
            get("https://im.qq.com/proxy/domain/cdn-go.cn/qq-web/im.qq.com_new/latest/rainbow/pcConfig.json")
        )["Windows"]
        return Version(self.config["version"])

    @override
    def get_comparison_version(self, version: Version) -> Version:
        return Version(version.value[:3])

    @override
    def get_update_version(self, version: Version) -> Version:
        digest = sha256()
        with TemporaryFile() as installer:
            with _download_signed(self.config["ntDownloadX64Url"]) as response:
                for chunk in response.iter_bytes():
                    installer.write(chunk)
                    digest.update(chunk)

            self.full_version = _get_exe_version(installer)
        assert self.get_comparison_version(self.full_version) == version
        self.x64_sha256 = digest.hexdigest().upper()
        return self.full_version

    @override
    def get_installers(self) -> list[Installer]:
        hashes = {"x64": self.x64_sha256}
        directories = {}
        for architecture, key in (("x86", "ntDownloadUrl"), ("arm64", "ntDownloadARMUrl")):
            digest = sha256()
            directory_hash = md5(usedforsecurity=False)
            with _download_signed(self.config[key]) as response:
                for chunk in response.iter_bytes():
                    digest.update(chunk)
                    directory_hash.update(chunk)
            hashes[architecture] = digest.hexdigest().upper()
            directories[architecture] = directory_hash.hexdigest()[:8]

        installers: list[Installer] = []
        for architecture in ("x86", "x64", "arm64"):
            directory = directories["arm64" if architecture == "arm64" else "x86"]
            url = f"https://qqdl.gtimg.cn/qqfile/QQNT/{self.config['version']}/beta/{directory}/QQ{self.full_version}_{architecture}.exe"
            digest = sha256()
            with CLIENT.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    digest.update(chunk)
            direct_hash = digest.hexdigest().upper()
            assert direct_hash == hashes[architecture], f"SHA256 mismatch for {architecture}: {hashes[architecture]} != {direct_hash}"
            sha256_cache[url] = direct_hash
            installers.append({"Architecture": architecture, "InstallerUrl": url})
        return installers

    @override
    def has_release_notes(self) -> bool:
        ip = socket.getaddrinfo("cdn-go.cn.cloud.tc.qq.com", 443, socket.AF_INET)[0][4][0]
        print(f"Fetching QQ release notes via {ip}")
        request = CLIENT.build_request(
            "GET", "https://cdn-go.cn/qq-web/im.qq.com_new/latest/rainbow/windowsLog.js"
        )
        request.extensions["sni_hostname"] = request.url.host
        request.url = request.url.copy_with(host=ip)
        config = CLIENT.send(request).raise_for_status().text
        start = config.index("var params= ") + len("var params= ")
        changelog = json.JSONDecoder().raw_decode(config[start:])[0]["log"]
        self.release = next(
            (release for release in changelog if release["version"].endswith(self.version)),
            None,
        )
        return bool(self.release)

    @override
    def get_update_args(self) -> UpdateArgs:
        args: UpdateArgs = {
            "base_version": self.old_version,
            "release_date": date.fromisoformat(self.config["updateDate"]),
        }
        if self.release:
            args["release_notes"] = {
                "zh-CN": ("\n".join(self.release["feature"]), "https://im.qq.com/pcqq/support.html")
            }
        return args

    @override
    def get_memo(self, old_memo: object | None) -> object:
        return None
