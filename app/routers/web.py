import datetime
import json
import secrets
from fastapi import APIRouter, Request, Form, Response, status, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db
from app.security import hash_password, verify_password, create_jwt_token, get_current_user_from_cookie

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["Web Portal"])

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user_from_cookie(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/pricing", status_code=302)

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@router.post("/login", response_class=HTMLResponse)
def login_action(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid email or password."})

    if user["is_suspended"]:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Account suspended. Please contact support."})

    token, _ = create_jwt_token(user["email"], f"{user['first_name']} {user['last_name']}", bool(user["is_admin"]), user["subscription_tier"])
    redirect = RedirectResponse("/dashboard", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(key="access_token", value=token, httponly=True, max_age=3600 * 24 * 7)
    return redirect

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"error": None})

@router.post("/register", response_class=HTMLResponse)
def register_action(request: Request, first_name: str = Form(...), last_name: str = Form(...),
                    email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower().strip(),))
    if cursor.fetchone():
        conn.close()
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Email is already registered."})

    hashed = hash_password(password)
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO users (email, password_hash, first_name, last_name, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (email.lower().strip(), hashed, first_name.strip(), last_name.strip(), now))
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
    if user["subscription_expires_at"]:
        try:
            exp_date = datetime.datetime.fromisoformat(user["subscription_expires_at"])
            delta = exp_date - datetime.datetime.utcnow()
            remaining_days = max(0, delta.days)
        except Exception:
            remaining_days = 0

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"user": user, "remaining_days": remaining_days}
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

    return templates.TemplateResponse(request=request, name="pricing.html", context={"user": user, "plans": plans})

# --- Checkout and Simulated Financial Gateway Flow ---

@router.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request, plan_id: str = Query("monthly")):
    user = get_current_user_from_cookie(request)
    if not user:
        return RedirectResponse(f"/login?next=/checkout?plan_id={plan_id}", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscription_plans WHERE id = ? AND is_active = 1", (plan_id,))
    plan = cursor.fetchone()
    conn.close()

    if not plan:
        return RedirectResponse("/pricing", status_code=302)

    return templates.TemplateResponse(request=request, name="checkout.html", context={"user": user, "plan": plan})

@router.post("/checkout/initiate")
def checkout_initiate(request: Request, plan_id: str = Form(...)):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (user_payload["email"],))
    user_row = cursor.fetchone()
    cursor.execute("SELECT * FROM subscription_plans WHERE id = ?", (plan_id,))
    plan = cursor.fetchone()

    if not user_row or not plan:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid checkout request.")

    now = datetime.datetime.utcnow().isoformat()
    ref_id = f"PAY-{secrets.token_hex(4).upper()}"
    cursor.execute("""
    INSERT INTO payments (user_id, plan_id, amount_toman, status, transaction_ref, created_at)
    VALUES (?, ?, ?, 'pending', ?, ?)
    """, (user_row["id"], plan["id"], plan["price_toman"], ref_id, now))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return RedirectResponse(f"/payment/gateway?payment_id={payment_id}", status_code=302)

@router.get("/payment/gateway", response_class=HTMLResponse)
def payment_gateway_page(request: Request, payment_id: int):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, sp.name as plan_name
    FROM payments p
    JOIN subscription_plans sp ON p.plan_id = sp.id
    WHERE p.id = ? AND p.status = 'pending'
    """, (payment_id,))
    payment = cursor.fetchone()
    conn.close()

    if not payment:
        return RedirectResponse("/dashboard", status_code=302)

    return templates.TemplateResponse(request=request, name="payment_gateway.html", context={"payment": payment})

@router.post("/payment/callback")
def payment_callback(request: Request, payment_id: int = Form(...), outcome: str = Form(...)):
    user_payload = get_current_user_from_cookie(request)
    if not user_payload:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    payment = cursor.fetchone()

    if not payment or payment["status"] != "pending":
        conn.close()
        return RedirectResponse("/dashboard", status_code=302)

    now = datetime.datetime.utcnow().isoformat()

    if outcome == "success":
        cursor.execute("SELECT duration_days FROM subscription_plans WHERE id = ?", (payment["plan_id"],))
        plan = cursor.fetchone()
        duration = plan["duration_days"] if plan else 30

        new_expiry = (datetime.datetime.utcnow() + datetime.timedelta(days=duration)).isoformat()

        cursor.execute("UPDATE payments SET status = 'completed', completed_at = ? WHERE id = ?", (now, payment_id))
        cursor.execute("UPDATE users SET subscription_tier = 'premium', subscription_expires_at = ? WHERE id = ?", (new_expiry, payment["user_id"]))
        conn.commit()
        conn.close()
        return RedirectResponse("/dashboard?payment=success", status_code=302)
    else:
        cursor.execute("UPDATE payments SET status = 'failed', completed_at = ? WHERE id = ?", (now, payment_id))
        conn.commit()
        conn.close()
        return RedirectResponse("/dashboard?payment=failed", status_code=302)