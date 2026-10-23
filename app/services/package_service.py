import os
import shutil
import hashlib
import zipfile
import json
from typing import List, Tuple
from fastapi import UploadFile
from PIL import Image
from app.config import PACKAGES_DIR, MEDIA_DIR

class PackageService:
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

        img = Image.open(icon_file.file).convert("RGBA")

        p32_path = os.path.join(asset_media_dir, "icon_32.png")
        p64_path = os.path.join(asset_media_dir, "icon_64.png")

        img.resize((32, 32), Image.Resampling.LANCZOS).save(p32_path, "PNG")
        img.resize((64, 64), Image.Resampling.LANCZOS).save(p64_path, "PNG")

        return f"/static/media/{slug}/icon_32.png", f"/static/media/{slug}/icon_64.png"

    @classmethod
    def save_media_items(cls, slug: str, media_files: List[UploadFile],
                         titles: List[str], descriptions: List[str]) -> List[dict]:
        asset_media_dir = os.path.join(MEDIA_DIR, slug)
        os.makedirs(asset_media_dir, exist_ok=True)

        results = []
        for idx, file in enumerate(media_files):
            if not file or not file.filename:
                continue

            safe_filename = f"media_{idx + 1}_{file.filename}"
            target_path = os.path.join(asset_media_dir, safe_filename)

            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            ext = os.path.splitext(file.filename)[1].lower()
            kind = "video" if ext in [".mp4", ".webm", ".avi", ".mov"] else "image"
            media_title = titles[idx] if idx < len(titles) and titles[idx].strip() else file.filename
            media_desc = descriptions[idx] if idx < len(descriptions) else ""
            media_url = f"/static/media/{slug}/{safe_filename}"

            results.append({
                "id": f"m{idx + 1}",
                "kind": kind,
                "title": media_title,
                "description": media_desc,
                "thumb_url": media_url if kind == "image" else "",
                "media_url": media_url
            })

        return results

    @classmethod
    def build_package_bundle(cls, slug: str, version: str, files: List[UploadFile],
                             entry_point: str, command: str, alias: str) -> dict:
        asset_dir = os.path.join(PACKAGES_DIR, slug)
        os.makedirs(asset_dir, exist_ok=True)

        version_filename = f"{version}.zip"
        version_filepath = os.path.join(asset_dir, version_filename)
        latest_filepath = os.path.join(asset_dir, "latest.zip")

        included_files = [f.filename for f in files if f.filename]

        with zipfile.ZipFile(version_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            package_manifest = {
                "slug": slug,
                "version": version,
                "entry_point": entry_point,
                "command": command,
                "alias": alias,
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
            "sha256": sha256_hash
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