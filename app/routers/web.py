import datetime
import json
from fastapi import APIRouter, Request, Form, Response, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from app.database import get_db
from app.security import hash_password, verify_password, create_jwt_token, get_current_user_from_cookie
from app.templates_config import templates

router = APIRouter(tags=["Web Portal"])

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user_from_cookie(request)
    if user:
        if user.get("is_admin"):
            return RedirectResponse("/admin", status_code=302)
        return RedirectResponse("/dashboard", status_code=302)
    # Redirect unauthenticated guests to pricing (or change to /login if preferred)
    return RedirectResponse("/pricing", status_code=302)

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

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user_payload["email"],))
    user = cursor.fetchone()
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
        context={"request": request, "user": user, "remaining_days": remaining_days}
    )

@router.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    user = get_current_user_from_cookie(request)
    if user and user.get("is_admin"):
        return RedirectResponse("/admin/plans", status_code=302)

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

@router.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request, plan_id: str = Query("monthly")):
    user = get_current_user_from_cookie(request)
    if user and user.get("is_admin"):
        return RedirectResponse("/admin", status_code=302)
    if not user:
        return RedirectResponse(f"/login?next=/checkout?plan_id={plan_id}", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
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