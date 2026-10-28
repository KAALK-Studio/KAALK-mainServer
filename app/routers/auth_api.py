# app/routers/auth_api.py
import datetime
import secrets
from fastapi import APIRouter, HTTPException, status, Request
from app.database import get_db
from app.security import hash_password, verify_password, create_jwt_token
from app.schemas import RegisterRequest, LoginRequest, ForgotPasswordRequest, AuthResponse

router = APIRouter(prefix="/api/auth", tags=["AutoCAD Auth API"])

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email.lower().strip(),))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Account already exists.")

    hashed = hash_password(req.password)
    now = datetime.datetime.utcnow().isoformat()
    client_ip = request.client.host if request.client else "127.0.0.1"

    cursor.execute("""
    INSERT INTO users (email, phone, password_hash, first_name, last_name, last_ip, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (req.email.lower().strip(), req.phone.strip(), hashed, req.firstName.strip(), req.lastName.strip(), client_ip, now))
    conn.commit()
    conn.close()

    display_name = f"{req.firstName.strip()} {req.lastName.strip()}".strip()
    token, expires_in = create_jwt_token(req.email.lower().strip(), display_name, False, "free")

    return AuthResponse(
        success=True, accessToken=token, refreshToken=secrets.token_hex(32),
        expiresIn=expires_in, userName=display_name, email=req.email.lower().strip(),
        phone=req.phone.strip(), isPro=False, subscriptionTier="free",
        subscriptionExpiresAt=None, remainingDays=0
    )

@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, password_hash, first_name, last_name, phone, is_admin,
           subscription_tier, subscription_expires_at
    FROM users WHERE email = ?
    """, (req.email.lower().strip(),))
    row = cursor.fetchone()

    if not row or not verify_password(req.password, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    client_ip = request.client.host if request.client else "127.0.0.1"
    cursor.execute("UPDATE users SET last_ip = ? WHERE id = ?", (client_ip, row["id"]))
    conn.commit()
    conn.close()

    is_admin = bool(row["is_admin"])
    tier = row["subscription_tier"] or "free"
    sub_expires_at = row["subscription_expires_at"]
    remaining_days = 0
    is_active_pro = is_admin

    if tier == "premium":
        if sub_expires_at:
            try:
                exp_dt = datetime.datetime.fromisoformat(sub_expires_at)
                diff = exp_dt - datetime.datetime.utcnow()
                if diff.total_seconds() > 0:
                    is_active_pro = True
                    remaining_days = int((diff.total_seconds() + 86399) // 86400)
                else:
                    is_active_pro = is_admin
            except Exception:
                is_active_pro = is_admin
        else:
            is_active_pro = True
            remaining_days = 0

    display_name = f"{row['first_name']} {row['last_name']}".strip()
    token, expires_in = create_jwt_token(
        req.email.lower().strip(),
        display_name,
        is_admin,
        "premium" if is_active_pro else "free"
    )

    return AuthResponse(
        success=True,
        accessToken=token,
        refreshToken=secrets.token_hex(32),
        expiresIn=expires_in,
        userName=display_name,
        email=req.email.lower().strip(),
        phone=row["phone"] or "",
        isPro=is_active_pro,
        subscriptionTier="premium" if is_active_pro else "free",
        subscriptionExpiresAt=sub_expires_at,
        remainingDays=remaining_days
    )
