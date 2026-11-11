# app/services/package_service.py
import os
import shutil
import hashlib
import zipfile
import json
import uuid
import struct
import re
import tempfile
import datetime
from typing import List, Tuple, Optional
from fastapi import UploadFile, HTTPException
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
            "download_url": f"/api/v1/packages/{slug}/{version}/download",
            "file_size": file_size,
            "sha256": sha256_hash,
            "commands": normalized_commands
        }

    @classmethod
    def update_version_package(cls, slug: str, old_version: str, new_version: str,
                               files: Optional[List[UploadFile]], entry_point: str,
                               commands: List[dict], asset_name: str = "",
                               is_latest: bool = True) -> dict:
        asset_dir = os.path.join(PACKAGES_DIR, slug)
        os.makedirs(asset_dir, exist_ok=True)

        old_zip_path = os.path.join(asset_dir, f"{old_version}.zip")
        new_zip_path = os.path.join(asset_dir, f"{new_version}.zip")
        latest_zip_path = os.path.join(asset_dir, "latest.zip")

        has_new_files = files and any(f.filename for f in files)

        if has_new_files:
            valid_files = [f for f in files if f.filename]
            res = cls.build_package_bundle(
                slug=slug,
                version=new_version,
                files=valid_files,
                entry_point=entry_point,
                commands=commands,
                asset_name=asset_name
            )
            if old_version != new_version and os.path.exists(old_zip_path):
                try:
                    os.remove(old_zip_path)
                except Exception:
                    pass
            return res

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

        file_bytes_map = {}
        target_source_zip = old_zip_path if os.path.exists(old_zip_path) else latest_zip_path

        if os.path.exists(target_source_zip):
            with zipfile.ZipFile(target_source_zip, "r") as zf:
                for name in zf.namelist():
                    if name != "package.json":
                        file_bytes_map[name] = zf.read(name)

        final_entry_point = entry_point.strip() if entry_point else ""
        if not final_entry_point and file_bytes_map:
            for fname in file_bytes_map.keys():
                if fname.lower().endswith(".dll"):
                    final_entry_point = fname
                    break

        package_manifest = {
            "slug": slug,
            "name": asset_name or slug,
            "version": new_version,
            "entry_point": final_entry_point,
            "commands": normalized_commands,
            "files": list(file_bytes_map.keys())
        }

        temp_zip_path = os.path.join(asset_dir, f"temp_{uuid.uuid4().hex[:8]}.zip")
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("package.json", json.dumps(package_manifest, indent=2))
            for fname, data in file_bytes_map.items():
                zf.writestr(fname, data)

        if os.path.exists(old_zip_path) and old_version != new_version:
            try:
                os.remove(old_zip_path)
            except Exception:
                pass

        if os.path.exists(new_zip_path):
            try:
                os.remove(new_zip_path)
            except Exception:
                pass

        shutil.move(temp_zip_path, new_zip_path)

        if is_latest:
            shutil.copy2(new_zip_path, latest_zip_path)

        file_size = os.path.getsize(new_zip_path)
        sha256_hash = cls.calculate_sha256(new_zip_path)

        return {
            "download_url": f"/api/v1/packages/{slug}/{new_version}/download",
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

    @classmethod
    def export_asset_bundle(cls, asset_id: str) -> Tuple[str, str]:
        from app.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM assets WHERE id = ? OR slug = ?", (asset_id, asset_id.lower().strip()))
        asset_row = cursor.fetchone()
        if not asset_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Asset not found.")

        asset = dict(asset_row)
        actual_id = asset["id"]
        slug = asset["slug"]

        cursor.execute("SELECT * FROM asset_versions WHERE asset_id = ? ORDER BY id ASC", (actual_id,))
        versions_rows = [dict(v) for v in cursor.fetchall()]
        conn.close()

        manifest = {
            "bundle_type": "kaalk_asset_package",
            "bundle_version": "1.0",
            "exported_at": datetime.datetime.utcnow().isoformat(),
            "asset": asset,
            "versions": versions_rows
        }

        temp_dir = tempfile.mkdtemp()
        bundle_filename = f"kaalk_asset_{slug}_bundle.zip"
        bundle_path = os.path.join(temp_dir, bundle_filename)

        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            # Include package zip archives
            asset_packages_dir = os.path.join(PACKAGES_DIR, slug)
            if os.path.exists(asset_packages_dir):
                for fname in os.listdir(asset_packages_dir):
                    fp = os.path.join(asset_packages_dir, fname)
                    if os.path.isfile(fp):
                        zf.write(fp, arcname=f"packages/{fname}")

            # Include media, icons, and tutorials
            asset_media_dir = os.path.join(MEDIA_DIR, slug)
            if os.path.exists(asset_media_dir):
                for fname in os.listdir(asset_media_dir):
                    fp = os.path.join(asset_media_dir, fname)
                    if os.path.isfile(fp):
                        zf.write(fp, arcname=f"media/{fname}")

        return bundle_path, bundle_filename

    @classmethod
    def import_asset_bundle(cls, bundle_file: UploadFile) -> Tuple[bool, str]:
        from app.database import get_db

        temp_dir = tempfile.mkdtemp()
        temp_zip_path = os.path.join(temp_dir, "import_bundle.zip")
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(bundle_file.file, buffer)

        if not zipfile.is_zipfile(temp_zip_path):
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP bundle.")

        with zipfile.ZipFile(temp_zip_path, "r") as zf:
            if "manifest.json" not in zf.namelist():
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail="Invalid bundle: manifest.json is missing.")

            manifest_content = zf.read("manifest.json").decode("utf-8")
            try:
                manifest = json.loads(manifest_content)
            except Exception as e:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail=f"Corrupt manifest.json: {str(e)}")

            asset_data = manifest.get("asset")
            versions_data = manifest.get("versions", [])

            if not asset_data or not asset_data.get("slug"):
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail="Invalid bundle: asset metadata is incomplete.")

            slug = asset_data["slug"].strip().lower()
            asset_id = asset_data.get("id") or cls.generate_asset_id(slug)

            target_packages_dir = os.path.join(PACKAGES_DIR, slug)
            target_media_dir = os.path.join(MEDIA_DIR, slug)
            os.makedirs(target_packages_dir, exist_ok=True)
            os.makedirs(target_media_dir, exist_ok=True)

            for member in zf.namelist():
                if member.startswith("packages/") and not member.endswith("/"):
                    fname = os.path.basename(member)
                    if fname:
                        dest = os.path.join(target_packages_dir, fname)
                        with open(dest, "wb") as f_out:
                            f_out.write(zf.read(member))
                elif member.startswith("media/") and not member.endswith("/"):
                    fname = os.path.basename(member)
                    if fname:
                        dest = os.path.join(target_media_dir, fname)
                        with open(dest, "wb") as f_out:
                            f_out.write(zf.read(member))

        shutil.rmtree(temp_dir, ignore_errors=True)

        conn = get_db()
        cursor = conn.cursor()
        now = datetime.datetime.utcnow().isoformat()

        cursor.execute("""
        INSERT INTO assets (id, slug, name, type, asset_status, min_autocad, short_desc, full_desc,
                            thumb_32_url, thumb_64_url, is_pro, commands_json, tags, media_json,
                            latest_version, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            slug=excluded.slug,
            name=excluded.name,
            type=excluded.type,
            asset_status=excluded.asset_status,
            min_autocad=excluded.min_autocad,
            short_desc=excluded.short_desc,
            full_desc=excluded.full_desc,
            thumb_32_url=excluded.thumb_32_url,
            thumb_64_url=excluded.thumb_64_url,
            is_pro=excluded.is_pro,
            commands_json=excluded.commands_json,
            tags=excluded.tags,
            media_json=excluded.media_json,
            latest_version=excluded.latest_version,
            updated_at=excluded.updated_at
        """, (
            asset_id,
            slug,
            asset_data.get("name", slug),
            asset_data.get("type", "tool"),
            asset_data.get("asset_status", "stable"),
            asset_data.get("min_autocad", 2018),
            asset_data.get("short_desc", ""),
            asset_data.get("full_desc", ""),
            asset_data.get("thumb_32_url", ""),
            asset_data.get("thumb_64_url", ""),
            1 if asset_data.get("is_pro") else 0,
            asset_data.get("commands_json", "[]"),
            asset_data.get("tags", ""),
            asset_data.get("media_json", "[]"),
            asset_data.get("latest_version", "0.1.0"),
            asset_data.get("created_at", now),
            now
        ))

        for v in versions_data:
            ver_num = v.get("version", "0.1.0")
            dl_url = f"/api/v1/packages/{slug}/{ver_num}/download"
            ver_zip = os.path.join(target_packages_dir, f"{ver_num}.zip")
            f_size = os.path.getsize(ver_zip) if os.path.exists(ver_zip) else v.get("file_size", 0)
            sha = cls.calculate_sha256(ver_zip) if os.path.exists(ver_zip) else v.get("sha256", "")

            cursor.execute("""
            INSERT INTO asset_versions (asset_id, version, release_notes, download_url, file_size, sha256, commands_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id, version) DO UPDATE SET
                release_notes=excluded.release_notes,
                download_url=excluded.download_url,
                file_size=excluded.file_size,
                sha256=excluded.sha256,
                commands_json=excluded.commands_json
            """, (
                asset_id,
                ver_num,
                v.get("release_notes", ""),
                dl_url,
                f_size,
                sha,
                v.get("commands_json", "[]"),
                v.get("created_at", now)
            ))

        conn.commit()
        conn.close()

        return True, asset_data.get("name", slug)