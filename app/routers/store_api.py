# app/routers/store_api.py
import json
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.database import get_db
from app.schemas import CommentCreateRequest, RatingCreateRequest

router = APIRouter(prefix="/api/v1", tags=["AutoCAD Store API"])

@router.get("/catalog")
def get_catalog(type: Optional[str] = Query(None)):
    conn = get_db()
    cursor = conn.cursor()
    query = """
    SELECT id, slug, name, type, latest_version, min_autocad, short_desc,
           thumb_32_url, thumb_64_url, is_pro, rating, dev_name, tags
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
        thumb_url = r["thumb_64_url"] or r["thumb_32_url"] or f"/static/media/{r['slug']}/icon_64.png"

        assets.append({
            "id": r["id"],
            "slug": r["slug"],
            "name": r["name"],
            "type": r["type"],
            "version": r["latest_version"] or "1.0.0",
            "min_autocad": r["min_autocad"],
            "short_desc": r["short_desc"] or "",
            "thumb_url": thumb_url,
            "is_pro": bool(r["is_pro"]),
            "rating": float(r["rating"]) if r["rating"] else 5.0,
            "dev": r["dev_name"] or "KAALK Studio",
            "tags": r["tags"] or ""
        })

    return {
        "catalog_version": "1.0",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
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

    cursor.execute("""
    SELECT author, text, created_at 
    FROM comments 
    WHERE asset_id = ? 
    ORDER BY id DESC 
    LIMIT 10
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
        "full_description": asset["full_desc"] or "",
        "default_command": asset["default_command"] or "",
        "default_alias": asset["default_alias"] or "",
        "developer": {
            "id": asset["dev_id"] or "dev_kaalk",
            "name": asset["dev_name"] or "KAALK Studio",
            "website": asset["dev_website"] or "https://kaalk.ir"
        },
        "stats": {
            "rating_count": asset["rating_count"],
            "download_count": asset["download_count"]
        },
        "versions": {
            "latest": asset["latest_version"] or "1.0.0",
            "selected": selected_version_data["version"] if selected_version_data else (asset["latest_version"] or "1.0.0"),
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
                    "created_at": c["created_at"]
                }
                for c in comment_rows
            ]
        },
        "updated_at": asset["updated_at"]
    }

# اندپوینت جدید: ثبت کامنت
@router.post("/assets/{asset_id}/comments", status_code=status.HTTP_201_CREATED)
def post_asset_comment(asset_id: str, payload: CommentCreateRequest):
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Comment text cannot be empty.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM assets WHERE id = ?", (asset_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO comments (asset_id, author, text, rating, created_at)
    VALUES (?, ?, ?, 5, ?)
    """, (asset_id, payload.author.strip() if payload.author else "You", payload.text.strip(), now))
    
    conn.commit()
    conn.close()
    return {"success": True, "message": "Comment posted successfully."}

# اندپوینت جدید: ثبت امتیاز و محاسبه میانگین
@router.post("/assets/{asset_id}/ratings")
def post_asset_rating(asset_id: str, payload: RatingCreateRequest):
    if payload.rating < 1 or payload.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT rating, rating_count FROM assets WHERE id = ?", (asset_id,))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    current_rating = asset["rating"] or 5.0
    current_count = asset["rating_count"] or 0

    new_count = current_count + 1
    new_rating = ((current_rating * current_count) + payload.rating) / new_count

    cursor.execute("""
    UPDATE assets SET rating = ?, rating_count = ? WHERE id = ?
    """, (round(new_rating, 1), new_count, asset_id))

    conn.commit()
    conn.close()
    return {"success": True, "rating": round(new_rating, 1), "rating_count": new_count}