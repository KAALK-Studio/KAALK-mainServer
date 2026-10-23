import json
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.database import get_db

router = APIRouter(prefix="/api/v1", tags=["AutoCAD Store API"])

@router.get("/catalog")
def get_catalog(type: Optional[str] = Query(None)):
    conn = get_db()
    cursor = conn.cursor()
    query = """
    SELECT id, slug, name, type, asset_status, latest_version, min_autocad, short_desc,
           thumb_32_url, thumb_64_url, is_pro, rating, rating_count, dev_name, tags
    FROM assets
    """
    params = ()
    if type:
        query += " WHERE type = ?"
        params = (type.lower().strip(),)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    assets = []
    for r in rows:
        assets.append({
            "id": r["id"],
            "slug": r["slug"],
            "name": r["name"],
            "type": r["type"],
            "status": r["asset_status"] or "stable",
            "version": r["latest_version"] or "1.0.0",
            "min_autocad": r["min_autocad"],
            "short_desc": r["short_desc"] or "",
            "thumb_32_url": r["thumb_32_url"] or "",
            "thumb_64_url": r["thumb_64_url"] or "",
            "is_pro": bool(r["is_pro"]),
            "rating": r["rating"],
            "rating_count": r["rating_count"],
            "dev": r["dev_name"] or "",
            "tags": r["tags"] or ""
        })

    return {
        "catalog_version": "1.0",
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "total_assets": len(assets),
        "assets": assets
    }

@router.get("/assets/{asset_id}")
def get_asset_detail(asset_id: str, version: Optional[str] = Query(None)):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    # Retrieve all versions for this asset
    cursor.execute("""
    SELECT version, release_notes, download_url, file_size, sha256, created_at
    FROM asset_versions WHERE asset_id = ? ORDER BY id DESC
    """, (asset_id,))
    versions_rows = cursor.fetchall()

    version_history = []
    selected_version_data = None
    target_ver = version or asset["latest_version"]

    for v in versions_rows:
        item = {
            "version": v["version"],
            "release_notes": v["release_notes"] or "",
            "download_url": v["download_url"],
            "file_size": v["file_size"],
            "sha256": v["sha256"],
            "created_at": v["created_at"]
        }
        version_history.append(item)
        if v["version"] == target_ver:
            selected_version_data = item

    if not selected_version_data and version_history:
        selected_version_data = version_history[0]

    # Retrieve latest comments with ratings
    cursor.execute("""
    SELECT author, text, rating, created_at 
    FROM comments 
    WHERE asset_id = ? 
    ORDER BY id DESC 
    LIMIT 5
    """, (asset_id,))
    comment_rows = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) as count FROM comments WHERE asset_id = ?", (asset_id,))
    total_comments = cursor.fetchone()["count"]
    conn.close()

    try:
        media_list = json.loads(asset["media_json"]) if asset["media_json"] else []
    except Exception:
        media_list = []

    return {
        "id": asset["id"],
        "slug": asset["slug"],
        "name": asset["name"],
        "type": asset["type"],
        "status": asset["asset_status"] or "stable",
        "full_description": asset["full_desc"] or "",
        "default_command": asset["default_command"] or "",
        "default_alias": asset["default_alias"] or "",
        "developer": {
            "id": asset["dev_id"] or "",
            "name": asset["dev_name"] or "",
            "website": asset["dev_website"] or ""
        },
        "stats": {
            "rating": asset["rating"],
            "rating_count": asset["rating_count"],
            "download_count": asset["download_count"],
            "monthly_downloads": asset["monthly_downloads"]
        },
        "versions": {
            "latest": asset["latest_version"] or "1.0.0",
            "selected": selected_version_data["version"] if selected_version_data else "1.0.0",
            "available": [v["version"] for v in version_history]
        },
        "package": {
            "download_url": selected_version_data["download_url"] if selected_version_data else "",
            "file_size": selected_version_data["file_size"] if selected_version_data else 0,
            "sha256": selected_version_data["sha256"] if selected_version_data else ""
        },
        "release_notes": selected_version_data["release_notes"] if selected_version_data else "",
        "version_history": version_history,
        "media": media_list,
        "comments_summary": {
            "total_count": total_comments,
            "latest_comments": [
                {
                    "author": c["author"],
                    "text": c["text"],
                    "rating": c["rating"],
                    "created_at": c["created_at"]
                }
                for c in comment_rows
            ]
        },
        "updated_at": asset["updated_at"]
    }