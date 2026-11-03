# app/services/package_service.py
import os
import shutil
import hashlib
import zipfile
import json
import uuid
import struct
import re
from typing import List, Tuple
from fastapi import UploadFile
from PIL import Image
from app.config import PACKAGES_DIR, MEDIA_DIR

class PackageService:
    @staticmethod
    def xxhash32(data: bytes, seed: int = 0) -> int:
        PRIME32_1 = 0x9E3779B1
        PRIME32_2 = 0x85EBCA77
        PRIME32_3 = 0xC2B2AE3D
        PRIME32_4 = 0x27D4EB2F
        PRIME32_5 = 0x165667B1

        length = len(data)
        if length >= 16:
            limit = length - 16
            v1 = (seed + PRIME32_1 + PRIME32_2) & 0xFFFFFFFF
            v2 = (seed + PRIME32_2) & 0xFFFFFFFF
            v3 = (seed + 0) & 0xFFFFFFFF
            v4 = (seed - PRIME32_1) & 0xFFFFFFFF

            offset = 0
            while offset <= limit:
                p1, p2, p3, p4 = struct.unpack_from('<4I', data, offset)
                v1 = (v1 + p1 * PRIME32_2) & 0xFFFFFFFF
                v1 = ((v1 << 13) | (v1 >> 19)) & 0xFFFFFFFF
                v1 = (v1 * PRIME32_1) & 0xFFFFFFFF

                v2 = (v2 + p2 * PRIME32_2) & 0xFFFFFFFF
                v2 = ((v2 << 13) | (v2 >> 19)) & 0xFFFFFFFF
                v2 = (v2 * PRIME32_1) & 0xFFFFFFFF

                v3 = (v3 + p3 * PRIME32_2) & 0xFFFFFFFF
                v3 = ((v3 << 13) | (v3 >> 19)) & 0xFFFFFFFF
                v3 = (v3 * PRIME32_1) & 0xFFFFFFFF

                v4 = (v4 + p4 * PRIME32_2) & 0xFFFFFFFF
                v4 = ((v4 << 13) | (v4 >> 19)) & 0xFFFFFFFF
                v4 = (v4 * PRIME32_1) & 0xFFFFFFFF
                offset += 16

            h32 = (((v1 << 1) | (v1 >> 31)) +
                   ((v2 << 7) | (v2 >> 25)) +
                   ((v3 << 12) | (v3 >> 20)) +
                   ((v4 << 18) | (v4 >> 14))) & 0xFFFFFFFF
        else:
            h32 = (seed + PRIME32_5) & 0xFFFFFFFF

        h32 = (h32 + length) & 0xFFFFFFFF

        offset = length - (length % 16) if length >= 16 else 0
        while offset <= length - 4:
            p = struct.unpack_from('<I', data, offset)[0]
            h32 = (h32 + p * PRIME32_3) & 0xFFFFFFFF
            h32 = ((h32 << 17) | (h32 >> 15)) & 0xFFFFFFFF
            h32 = (h32 * PRIME32_4) & 0xFFFFFFFF
            offset += 4

        while offset < length:
            h32 = (h32 + data[offset] * PRIME32_5) & 0xFFFFFFFF
            h32 = ((h32 << 11) | (h32 >> 21)) & 0xFFFFFFFF
            h32 = (h32 * PRIME32_1) & 0xFFFFFFFF
            offset += 1

        h32 = (h32 ^ (h32 >> 15)) & 0xFFFFFFFF
        h32 = (h32 * PRIME32_2) & 0xFFFFFFFF
        h32 = (h32 ^ (h32 >> 13)) & 0xFFFFFFFF
        h32 = (h32 * PRIME32_3) & 0xFFFFFFFF
        h32 = (h32 ^ (h32 >> 16)) & 0xFFFFFFFF

        return h32

    @classmethod
    def generate_asset_id(cls, slug: str) -> str:
        clean_slug = slug.strip().lower()
        hash_val = cls.xxhash32(clean_slug.encode("utf-8"))
        return f"{hash_val:08x}"

    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def process_icon(cls, slug: str, icon_file: UploadFile) -> Tuple[str, str]:
        asset_media_dir = os.path.join(MEDIA_DIR, slug)
        os.makedirs(asset_media_dir, exist_ok=True)

        uid = uuid.uuid4().hex[:8]
        img = Image.open(icon_file.file).convert("RGBA")

        p32_name = f"icon_32_{uid}.png"
        p64_name = f"icon_64_{uid}.png"
        p32_path = os.path.join(asset_media_dir, p32_name)
        p64_path = os.path.join(asset_media_dir, p64_name)

        img.resize((32, 32), Image.Resampling.LANCZOS).save(p32_path, "PNG")
        img.resize((64, 64), Image.Resampling.LANCZOS).save(p64_path, "PNG")

        return f"/static/media/{slug}/{p32_name}", f"/static/media/{slug}/{p64_name}"

    @classmethod
    def save_media_items(cls, slug: str, media_files: List[UploadFile],
                         titles: List[str], descriptions: List[str]) -> List[dict]:
        asset_media_dir = os.path.join(MEDIA_DIR, slug)
        os.makedirs(asset_media_dir, exist_ok=True)

        results = []
        for idx, file in enumerate(media_files):
            if not file or not file.filename:
                continue

            uid = uuid.uuid4().hex[:8]
            ext = os.path.splitext(file.filename)[1].lower()
            safe_filename = f"media_{uid}_{file.filename}"
            target_path = os.path.join(asset_media_dir, safe_filename)

            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            kind = "video" if ext in [".mp4", ".webm", ".avi", ".mov"] else "image"
            media_title = titles[idx] if idx < len(titles) and titles[idx].strip() else file.filename
            media_desc = descriptions[idx] if idx < len(descriptions) else ""
            media_url = f"/static/media/{slug}/{safe_filename}"

            thumb_url = media_url
            if kind == "image":
                try:
                    thumb_name = f"thumb_64_{uid}.png"
                    thumb_path = os.path.join(asset_media_dir, thumb_name)
                    with Image.open(target_path) as src_img:
                        thumb_img = src_img.convert("RGBA")
                        thumb_img.resize((64, 64), Image.Resampling.LANCZOS).save(thumb_path, "PNG")
                    thumb_url = f"/static/media/{slug}/{thumb_name}"
                except Exception:
                    thumb_url = media_url

            results.append({
                "id": f"m_{uid}",
                "kind": kind,
                "title": media_title,
                "description": media_desc,
                "thumb_url": thumb_url,
                "media_url": media_url
            })

        return results

    @classmethod
    def build_package_bundle(cls, slug: str, version: str, files: List[UploadFile],
                             entry_point: str, commands: List[dict], asset_name: str = "") -> dict:
        asset_dir = os.path.join(PACKAGES_DIR, slug)
        os.makedirs(asset_dir, exist_ok=True)

        version_filename = f"{version}.zip"
        version_filepath = os.path.join(asset_dir, version_filename)
        latest_filepath = os.path.join(asset_dir, "latest.zip")

        included_files = [f.filename for f in files if f.filename]

        normalized_commands = []
        for cmd in commands:
            if isinstance(cmd, dict) and cmd.get("command"):
                raw_alias = str(cmd.get("alias", "")).strip().upper()
                alias_parts = [p.strip() for p in re.split(r"[,;]+", raw_alias) if p.strip()]
                normalized_alias = ", ".join(alias_parts)

                normalized_commands.append({
                    "command": str(cmd.get("command", "")).strip().upper(),
                    "alias": normalized_alias,
                    "title": str(cmd.get("title", "")).strip(),
                    "status": str(cmd.get("status", "stable")).strip().lower(),
                    "description": str(cmd.get("description", "")).strip(),
                    "deprecation_notice": str(cmd.get("deprecation_notice", "")).strip()
                })

        with zipfile.ZipFile(version_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            package_manifest = {
                "slug": slug,
                "name": asset_name or slug,
                "version": version,
                "entry_point": entry_point,
                "commands": normalized_commands,
                "files": included_files
            }
            zf.writestr("package.json", json.dumps(package_manifest, indent=2))

            for f in files:
                if f.filename:
                    f.file.seek(0)
                    content = f.file.read()
                    zf.writestr(f.filename, content)

        shutil.copy2(version_filepath, latest_filepath)

        file_size = os.path.getsize(version_filepath)
        sha256_hash = cls.calculate_sha256(version_filepath)

        return {
            "download_url": f"/static/packages/{slug}/{version_filename}",
            "file_size": file_size,
            "sha256": sha256_hash,
            "commands": normalized_commands
        }

    @classmethod
    def delete_version_archive(cls, slug: str, version: str, remaining_versions: List[str]):
        asset_dir = os.path.join(PACKAGES_DIR, slug)
        version_filepath = os.path.join(asset_dir, f"{version}.zip")
        if os.path.exists(version_filepath):
            os.remove(version_filepath)

        latest_filepath = os.path.join(asset_dir, "latest.zip")
        if remaining_versions:
            new_latest_version = remaining_versions[0]
            new_latest_filepath = os.path.join(asset_dir, f"{new_latest_version}.zip")
            if os.path.exists(new_latest_filepath):
                shutil.copy2(new_latest_filepath, latest_filepath)
        else:
            if os.path.exists(latest_filepath):
                os.remove(latest_filepath)
