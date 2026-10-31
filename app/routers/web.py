# app/routers/web.py
import os
import datetime
import json
from typing import Optional
from fastapi import APIRouter, Request, Form, Response, status, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from app.config import DOWNLOADS_DIR, PACKAGES_DIR
from app.database import get_db
from app.security import hash_password, verify_password, create_jwt_token, get_current_user_from_cookie
from app.services.payment_service import PaymentGatewayService
from app.templates_config import templates

router = APIRouter(tags=["Web Portal"])

# --- Home & Marketing ---

@router.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, slug, name, type, short_desc, thumb_64_url, thumb_32_url, is_pro, rating, download_count 
    FROM assets ORDER BY download_count DESC LIMIT 6
    """)
    featured_assets = cursor.fetchall()

    cursor.execute("SELECT * FROM subscription_plans WHERE is_active = 1 ORDER BY price_toman ASC LIMIT 3")
    plans = cursor.fetchall()
    formatted_plans = []
    for p in plans:
        item = dict(p)
        item["features"] = json.loads(p["features_json"]) if p["features_json"] else []
        formatted_plans.append(item)

    cursor.execute("SELECT slug, title, summary, category, created_at FROM articles WHERE is_published = 1 ORDER BY id DESC LIMIT 3")
    articles = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as c FROM assets")
    asset_count = cursor.fetchone()["c"] or 0

    cursor.execute("SELECT COUNT(*) as c FROM users")
    user_count = cursor.fetchone()["c"] or 0

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "request": request,
            "user": user,
            "featured_assets": featured_assets,
            "plans": formatted_plans,
            "articles": articles,
            "stats": {"assets": asset_count, "users": user_count}
        }
    )

# --- Plugin Download Portal ---

@router.get("/download", response_class=HTMLResponse)
def download_page(request: Request):
    user = get_current_user_from_cookie(request)
    return templates.TemplateResponse(
        request=request,
        name="download.html",
        context={"request": request, "user": user, "version": "0.5.2"}
    )

@router.get("/download/file")
def download_plugin_file():
    target_zip = os.path.join(DOWNLOADS_DIR, "KaalkAssetManager.zip")
    if not os.path.exists(target_zip):
        # Create lightweight bundle placeholder if missing
        import zipfile
        with zipfile.ZipFile(target_zip, "w") as zf:
            zf.writestr("README.txt", "KAALK Asset Manager Plugin Client for AutoCAD 2018+\nRun NETLOAD in AutoCAD and select KaalkAssetManager.dll.\nType KAALK to open.")
    return FileResponse(target_zip, filename="KaalkAssetManager.zip", media_type="application/zip")

# --- Showcase Store (No Browser Downloads) ---

@router.get("/store", response_class=HTMLResponse)
def store_showcase(request: Request, type: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM assets"
    conditions = []
    params = []

    if type:
        conditions.append("type = ?")
        params.append(type.strip().lower())
    if search:
        conditions.append("(name LIKE ? OR short_desc LIKE ? OR tags LIKE ?)")
        s = f"%{search.strip()}%"
        params.extend([s, s, s])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY download_count DESC"
    cursor.execute(query, tuple(params))
    assets = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="store.html",
        context={
            "request": request,
            "user": user,
            "assets": assets,
            "selected_type": type or "",
            "search_query": search or ""
        }
    )

@router.get("/store/{slug}", response_class=HTMLResponse)
def store_asset_detail(request: Request, slug: str):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM assets WHERE slug = ?", (slug.strip().lower(),))
    asset = cursor.fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Asset not found.")

    asset_dict = dict(asset)
    try:
        media_items = json.loads(asset_dict.get("media_json") or "[]")
    except Exception:
        media_items = []

    try:
        commands_list = json.loads(asset_dict.get("commands_json") or "[]")
    except Exception:
        commands_list = []

    cursor.execute("SELECT * FROM asset_versions WHERE asset_id = ? ORDER BY id DESC", (asset["id"],))
    versions = cursor.fetchall()

    cursor.execute("SELECT author, text, rating, created_at FROM comments WHERE asset_id = ? ORDER BY id DESC LIMIT 10", (asset["id"],))
    comments = cursor.fetchall()
    conn.close()

    asset_dict["media_items"] = media_items
    asset_dict["commands_list"] = commands_list

    return templates.TemplateResponse(
        request=request,
        name="asset_detail.html",
        context={
            "request": request,
            "user": user,
            "asset": asset_dict,
            "versions": versions,
            "comments": comments
        }
    )

# --- Blog & Articles ---

@router.get("/blog", response_class=HTMLResponse)
def blog_list(request: Request, category: Optional[str] = Query(None)):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM articles WHERE is_published = 1"
    params = []
    if category:
        query += " AND category = ?"
        params.append(category.strip())

    query += " ORDER BY id DESC"
    cursor.execute(query, tuple(params))
    articles = cursor.fetchall()

    cursor.execute("SELECT DISTINCT category FROM articles WHERE is_published = 1")
    categories = [r["category"] for r in cursor.fetchall() if r["category"]]
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="blog.html",
        context={
            "request": request,
            "user": user,
            "articles": articles,
            "categories": categories,
            "selected_cat": category or ""
        }
    )

@router.get("/blog/{slug}", response_class=HTMLResponse)
def blog_article(request: Request, slug: str):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM articles WHERE slug = ? AND is_published = 1", (slug.strip().lower(),))
    article = cursor.fetchone()
    if not article:
        conn.close()
        raise HTTPException(status_code=404, detail="Article not found.")

    cursor.execute("UPDATE articles SET view_count = view_count + 1 WHERE id = ?", (article["id"],))
    conn.commit()

    cursor.execute("SELECT slug, title, category, created_at FROM articles WHERE is_published = 1 AND id != ? ORDER BY id DESC LIMIT 3", (article["id"],))
    recent = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="blog_detail.html",
        context={"request": request, "user": user, "article": article, "recent": recent}
    )

# --- About & Contact ---

@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    user = get_current_user_from_cookie(request)
    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={"request": request, "user": user}
    )

@router.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    user = get_current_user_from_cookie(request)
    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={"request": request, "user": user, "success": None, "error": None}
    )

@router.post("/contact", response_class=HTMLResponse)
def contact_submit(request: Request,
                   name: str = Form(...),
                   email: str = Form(...),
                   subject: str = Form(...),
                   message: str = Form(...)):
    user = get_current_user_from_cookie(request)
    name_clean = name.strip()
    email_clean = email.strip().lower()
    subject_clean = subject.strip()
    message_clean = message.strip()

    if not name_clean or not email_clean or not message_clean:
        return templates.TemplateResponse(
            request=request,
            name="contact.html",
            context={"request": request, "user": user, "error": "Please fill in all required fields.", "success": None}
        )

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO contact_inquiries (name, email, subject, message, is_resolved, created_at)
    VALUES (?, ?, ?, ?, 0, ?)
    """, (name_clean, email_clean, subject_clean, message_clean, now))
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={"request": request, "user": user, "success": "Thank you! Your message has been received.", "error": None}
    )

# --- Authentication ---

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "error": None}
    )

@router.post("/login", response_class=HTMLResponse)
def login_action(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    user = cursor.fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Invalid email or password."}
        )

    if user["is_suspended"]:
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Account suspended. Please contact support."}
        )

    client_ip = request.client.host if request.client else "127.0.0.1"
    cursor.execute("UPDATE users SET last_ip = ? WHERE id = ?", (client_ip, user["id"]))
    conn.commit()
    conn.close()

    token, _ = create_jwt_token(
        user["email"],
        f"{user['first_name']} {user['last_name']}",
        bool(user["is_admin"]),
        user["subscription_tier"]
    )
    target = "/admin" if user["is_admin"] else "/dashboard"
    redirect = RedirectResponse(target, status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(key="access_token", value=token, httponly=True, max_age=3600 * 24 * 7)
    return redirect

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"request": request, "error": None}
    )

@router.post("/register", response_class=HTMLResponse)
def register_action(request: Request, first_name: str = Form(...), last_name: str = Form(...),
                    email: str = Form(...), phone: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower().strip(),))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"request": request, "error": "Email is already registered."}
        )

    hashed = hash_password(password)
    now = datetime.datetime.utcnow().isoformat()
    client_ip = request.client.host if request.client else "127.0.0.1"

    cursor.execute("""
    INSERT INTO users (email, phone, password_hash, first_name, last_name, last_ip, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (email.lower().strip(), phone.strip(), hashed, first_name.strip(), last_name.strip(), client_ip, now))
    conn.commit()
    conn.close()

    return RedirectResponse("/login?registered=1", status_code=status.HTTP_302_FOUND)

@router.get("/logout")
def logout():
    redirect = RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie("access_token")
    return redirect

# --- User Dashboard & Billing ---

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user_payload["email"],))
    user = cursor.fetchone()

    cursor.execute("""
    SELECT p.*, s.name as plan_name 
    FROM payments p 
    JOIN subscription_plans s ON p.plan_id = s.id 
    WHERE p.user_id = ? ORDER BY p.id DESC LIMIT 5
    """, (user["id"],))
    payments = cursor.fetchall()
    conn.close()

    remaining_days = 0
    if user and user["subscription_expires_at"]:
        try:
            exp_date = datetime.datetime.fromisoformat(user["subscription_expires_at"])
            delta = exp_date - datetime.datetime.utcnow()
            remaining_days = max(0, delta.days)
        except Exception:
            remaining_days = 0

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"request": request, "user": user, "remaining_days": remaining_days, "payments": payments}
    )

@router.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    user = get_current_user_from_cookie(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscription_plans WHERE is_active = 1 ORDER BY price_toman ASC")
    plan_rows = cursor.fetchall()
    conn.close()

    plans = []
    for p in plan_rows:
        item = dict(p)
        item["features"] = json.loads(p["features_json"]) if p["features_json"] else []
        plans.append(item)

    return templates.TemplateResponse(
        request=request,
        name="pricing.html",
        context={"request": request, "user": user, "plans": plans}
    )

# --- Checkout & ZarinPal Gateway Flow ---

@router.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request, plan_id: str = Query("monthly")):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse(f"/login?next=/checkout?plan_id={plan_id}", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user_payload["email"],))
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM subscription_plans WHERE id = ? AND is_active = 1", (plan_id,))
    plan = cursor.fetchone()
    conn.close()

    if not plan:
        return RedirectResponse("/pricing", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={"request": request, "user": user, "plan": plan}
    )

@router.post("/checkout/pay")
def checkout_pay(request: Request, plan_id: str = Form(...)):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user_payload["email"],))
    user = cursor.fetchone()

    cursor.execute("SELECT * FROM subscription_plans WHERE id = ? AND is_active = 1", (plan_id,))
    plan = cursor.fetchone()

    if not user or not plan:
        conn.close()
        return RedirectResponse("/pricing", status_code=302)

    amount_toman = plan["price_toman"]
    if plan["discount_percent"] > 0:
        amount_toman = int(amount_toman * (100 - plan["discount_percent"]) / 100)

    callback_url = f"{str(request.base_url).rstrip('/')}/payment/callback"
    gateway_resp = PaymentGatewayService.initiate_transaction(
        amount_toman=amount_toman,
        description=f"KAALK {plan['name']} Subscription",
        callback_url=callback_url,
        email=user["email"],
        phone=user["phone"]
    )

    authority = gateway_resp["authority"]
    now = datetime.datetime.utcnow().isoformat()

    cursor.execute("""
    INSERT INTO payments (user_id, plan_id, amount_toman, gateway, authority, status, created_at)
    VALUES (?, ?, ?, 'zarinpal', ?, 'pending', ?)
    """, (user["id"], plan["id"], amount_toman, authority, now))
    conn.commit()
    conn.close()

    return RedirectResponse(gateway_resp["payment_url"], status_code=303)

@router.get("/payment/gateway", response_class=HTMLResponse)
def simulated_gateway_view(request: Request, authority: str = Query(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, s.name as plan_name 
    FROM payments p 
    JOIN subscription_plans s ON p.plan_id = s.id 
    WHERE p.authority = ?
    """, (authority,))
    payment = cursor.fetchone()
    conn.close()

    if not payment:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    return templates.TemplateResponse(
        request=request,
        name="payment_gateway.html",
        context={"request": request, "payment": payment}
    )

@router.post("/payment/gateway/submit")
def simulated_gateway_submit(payment_id: int = Form(...), outcome: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT authority FROM payments WHERE id = ?", (payment_id,))
    row = cursor.fetchone()
    conn.close()

    auth = row["authority"] if row else ""
    status_flag = "OK" if outcome == "success" else "NOK"
    return RedirectResponse(f"/payment/callback?Authority={auth}&Status={status_flag}", status_code=303)

@router.get("/payment/callback", response_class=HTMLResponse)
def payment_callback(request: Request, Authority: str = Query(...), Status: str = Query("NOK")):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, s.name as plan_name, s.duration_days, u.subscription_expires_at, u.email as user_email
    FROM payments p 
    JOIN subscription_plans s ON p.plan_id = s.id 
    JOIN users u ON p.user_id = u.id
    WHERE p.authority = ?
    """, (Authority,))
    payment = cursor.fetchone()

    if not payment:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction record not found.")

    if Status != "OK":
        cursor.execute("UPDATE payments SET status = 'cancelled' WHERE id = ?", (payment["id"],))
        conn.commit()
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="payment_result.html",
            context={"request": request, "success": False, "payment": payment, "ref_id": "", "message": "Transaction was cancelled by user."}
        )

    verify_res = PaymentGatewayService.verify_transaction(Authority, payment["amount_toman"])
    now = datetime.datetime.utcnow().isoformat()

    if verify_res["success"]:
        ref_id = verify_res["ref_id"]
        cursor.execute("UPDATE payments SET status = 'completed', transaction_ref = ?, completed_at = ? WHERE id = ?", (ref_id, now, payment["id"]))

        current_exp = payment["subscription_expires_at"]
        base_date = datetime.datetime.utcnow()
        if current_exp:
            try:
                parsed_cur = datetime.datetime.fromisoformat(current_exp)
                if parsed_cur > base_date:
                    base_date = parsed_cur
            except Exception:
                pass

        new_expiry = (base_date + datetime.timedelta(days=payment["duration_days"])).isoformat()
        cursor.execute("UPDATE users SET subscription_tier = 'premium', subscription_expires_at = ? WHERE id = ?", (new_expiry, payment["user_id"]))
        conn.commit()
        conn.close()

        return templates.TemplateResponse(
            request=request,
            name="payment_result.html",
            context={"request": request, "success": True, "payment": payment, "ref_id": ref_id, "message": verify_res["message"]}
        )
    else:
        cursor.execute("UPDATE payments SET status = 'failed' WHERE id = ?", (payment["id"],))
        conn.commit()
        conn.close()

        return templates.TemplateResponse(
            request=request,
            name="payment_result.html",
            context={"request": request, "success": False, "payment": payment, "ref_id": "", "message": verify_res["message"]}
        )
