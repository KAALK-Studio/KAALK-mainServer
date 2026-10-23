import datetime
import secrets
from fastapi import APIRouter, HTTPException, status
from app.database import get_db
from app.security import hash_password, verify_password, create_jwt_token
from app.schemas import RegisterRequest, LoginRequest, ForgotPasswordRequest, AuthResponse

router = APIRouter(prefix="/api/auth", tags=["AutoCAD Auth API"])

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email.lower().strip(),))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Account already exists.")

    hashed = hash_password(req.password)
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO users (email, password_hash, first_name, last_name, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (req.email.lower().strip(), hashed, req.firstName.strip(), req.lastName.strip(), now))
    conn.commit()
    conn.close()

    display_name = f"{req.firstName.strip()} {req.lastName.strip()}".strip()
    token, expires_in = create_jwt_token(req.email.lower().strip(), display_name, False, "free")

    return AuthResponse(
        success=True, accessToken=token, refreshToken=secrets.token_hex(32),
        expiresIn=expires_in, userName=display_name, email=req.email.lower().strip(), isPro=False
    )

@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, first_name, last_name, is_admin, subscription_tier, subscription_expires_at FROM users WHERE email = ?",
                   (req.email.lower().strip(),))
    row = cursor.fetchone()
    conn.close()

    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    is_pro = (row["subscription_tier"] == "premium")
    display_name = f"{row['first_name']} {row['last_name']}".strip()
    token, expires_in = create_jwt_token(req.email.lower().strip(), display_name, bool(row["is_admin"]), row["subscription_tier"])

    return AuthResponse(
        success=True, accessToken=token, refreshToken=secrets.token_hex(32),
        expiresIn=expires_in, userName=display_name, email=req.email.lower().strip(), isPro=is_pro
    )

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    return {"success": True, "message": "Instructions sent if email exists."}