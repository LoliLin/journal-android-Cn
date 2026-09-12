#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 fastlane/metadata/android 的商品文案（可选图片）上传到 Google Play。

CI 走的是 `bundle exec fastlane deploy`（见 .github/workflows/build-release.yml）；
这个脚本是**本地没有 Ruby / 装不了 fastlane 时**的等价物——supply 底层调的就是同一套
Play Developer API。

    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple google-auth
    python docs/scripts/upload_play_metadata.py --dry-run     # 只打印计划
    python docs/scripts/upload_play_metadata.py              # 上传文案
    python docs/scripts/upload_play_metadata.py --images     # 文案 + 图片

凭据：仓库根目录的 google-play-api.json（已被 .gitignore 忽略）。服务账号必须先在
Play Console 的「用户和权限」里被邀请，并授予该应用的「管理商店信息」（文案/图片）与
「发布到测试轨道」（AAB/changelog）权限，否则所有调用都会返回 403 PERMISSION_DENIED。

不在这里传的东西：
  * 按 versionCode 命名的 changelog：它挂在轨道的 release 上，随 AAB 一起提交；
  * 签名的 AAB：本机没有 keystore secrets，由 CI 构建后经 fastlane 上传。
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

from _common import die

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKAGE = "in.kawaiis.journal"
LOCALES = ("en-US", "zh-CN", "zh-TW")
METADATA_DIR = REPO_ROOT / "fastlane" / "metadata" / "android"
API_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
UPLOAD_BASE = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications"

#: 文件名 -> Play 的 imageType；其余名字是仓库素材，不上传（例如那张 10020x3440 的
#: "Google Pixel 4 XL Presentation.png"，既不是图标也不是 feature graphic）。
IMAGE_FILES = {
    "icon.png": "icon",
    "featureGraphic.png": "featureGraphic",
    "promoGraphic.png": "promoGraphic",
}

#: 文案字段 -> fastlane 的文件名
TEXT_FILES = (
    ("title", "title.txt"),
    ("shortDescription", "short_description.txt"),
    ("fullDescription", "full_description.txt"),
)


def png_size(path: Path) -> tuple:
    head = path.open("rb").read(24)
    return struct.unpack(">II", head[16:24])


def file_sha1(path: Path) -> str:
    """本地图片的 sha1，用来和线上比对（Play 的 images.list 会返回 sha1）。"""
    return hashlib.sha1(path.read_bytes()).hexdigest()


def content_type(path: Path) -> str:
    """按魔数判断类型，别一律当 PNG 发。"""
    head = path.open("rb").read(12)
    if head[:4] == b"\x89PNG":
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def local_plan() -> dict:
    """读出本地要上传的内容：{语言: {"text": {...}, "images": {imageType: [路径]}}}。"""
    plan = {}
    for lang in LOCALES:
        directory = METADATA_DIR / lang
        if not directory.is_dir():
            continue
        entry = {"text": {}, "images": {}}
        for field, filename in TEXT_FILES:
            path = directory / filename
            if path.exists() and path.read_text(encoding="utf-8").strip():
                entry["text"][field] = path.read_text(encoding="utf-8").strip()
        for path in sorted((directory / "images").glob("*.png")):
            if path.name in IMAGE_FILES:
                entry["images"].setdefault(IMAGE_FILES[path.name], []).append(path)
            else:
                width, height = png_size(path)
                print(f"跳过（不是 Play 认识的图片名）: {path.relative_to(METADATA_DIR)} {width}x{height}")
        screenshots = sorted((directory / "images" / "phoneScreenshots").glob("*.png"))
        if screenshots:
            entry["images"]["phoneScreenshots"] = screenshots
        plan[lang] = entry
    return plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", default=DEFAULT_PACKAGE, help=f"应用包名（默认 {DEFAULT_PACKAGE}）")
    parser.add_argument("--key", default=str(REPO_ROOT / "google-play-api.json"),
                        help="服务账号密钥（默认 <repo>/google-play-api.json）")
    parser.add_argument("--images", action="store_true", help="连图片一起上传（会先清空该语言该类型的线上图片）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不调用 Play API")
    args = parser.parse_args(argv)

    key_file = Path(args.key)
    if not key_file.exists():
        die(f"找不到服务账号密钥 '{key_file}'。")

    plan = local_plan()
    if not plan:
        die(f"'{METADATA_DIR}' 下没有可上传的语言目录。")
    summary = {lang: {"文案": len(entry["text"]), "图片": {k: len(v) for k, v in entry["images"].items()}}
               for lang, entry in plan.items()}
    print(f"本地计划：{summary}")
    if args.dry_run:
        print("--dry-run：没有调用 Play API。")
        return 0

    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError:
        die("缺少 google-auth：pip install -i https://pypi.tuna.tsinghua.edu.cn/simple google-auth")

    credentials = service_account.Credentials.from_service_account_file(
        str(key_file), scopes=["https://www.googleapis.com/auth/androidpublisher"])
    http = AuthorizedSession(credentials)
    base = f"{API_BASE}/{args.package}"

    response = http.post(f"{base}/edits")
    if response.status_code != 200:
        die(f"创建 edit 失败：HTTP {response.status_code}\n{response.text[:800]}\n"
            "→ 服务账号需要在 Play Console「用户和权限」里被邀请并授予应用权限。")
    edit = response.json()["id"]
    print(f"edit={edit}")

    live = {item["language"]: item
            for item in http.get(f"{base}/edits/{edit}/listings").json().get("listings", [])}
    changes = 0
    try:
        for lang, entry in plan.items():
            current = live.get(lang, {})
            body = {field: value for field, value in entry["text"].items() if current.get(field) != value}
            if body:
                response = http.patch(f"{base}/edits/{edit}/listings/{lang}", json=body)
                if response.status_code in (400, 404):  # 该语言还没有 listing：创建它
                    response = http.put(f"{base}/edits/{edit}/listings/{lang}", json=body)
                response.raise_for_status()
                print(f"  [{lang}] 文案更新：{sorted(body)}" + ("（新建 listing）" if lang not in live else ""))
                changes += 1
            else:
                print(f"  [{lang}] 文案已一致")
            if not args.images:
                continue
            for image_type, files in entry["images"].items():
                live_images = http.get(f"{base}/edits/{edit}/listings/{lang}/{image_type}").json().get("images", [])
                live_sha1 = sorted(item.get("sha1", "").lower() for item in live_images)
                local_sha1 = sorted(file_sha1(path) for path in files)
                if live_sha1 == local_sha1:
                    print(f"  [{lang}] {image_type}: 与线上一致，跳过")
                    continue
                http.delete(f"{base}/edits/{edit}/listings/{lang}/{image_type}").raise_for_status()
                for path in files:
                    # 图片走 Google 的上传端点（/upload/ 前缀 + uploadType=media），不是普通 REST 路径
                    response = http.post(
                        f"{UPLOAD_BASE}/{args.package}/edits/{edit}/listings/{lang}/{image_type}",
                        params={"uploadType": "media"},
                        headers={"Content-Type": content_type(path)},
                        data=path.read_bytes())
                    response.raise_for_status()
                print(f"  [{lang}] {image_type}: 上传 {len(files)} 张")
                changes += 1
    except Exception:
        http.delete(f"{base}/edits/{edit}")  # 出错就丢弃，线上保持原样
        raise

    validation = http.post(f"{base}/edits/{edit}:validate")
    if validation.status_code != 200:
        http.delete(f"{base}/edits/{edit}")
        die(f"校验失败（已丢弃 edit）：HTTP {validation.status_code}\n{validation.text[:800]}")

    commit = http.post(f"{base}/edits/{edit}:commit")
    if commit.status_code != 200:
        die(f"提交失败：HTTP {commit.status_code}\n{commit.text[:800]}")
    print(f"完成：{changes} 处改动已提交到 Google Play。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
