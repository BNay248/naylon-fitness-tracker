from fastapi import FastAPI, Request, Response, Cookie, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, date, time, timedelta, timezone
from db_manager import TrainerDB
from pydantic import BaseModel
from collections import defaultdict, deque
from typing import Dict
from urllib.parse import urlparse
from jose import jwt, JWTError
import bcrypt
import os
import re

app = FastAPI()
db = TrainerDB()

# Signs login cookies, so it must be private: required from the environment, never defaulted.
SECRET = os.environ.get("JWT_SECRET", "")
if len(SECRET) < 32:
    raise RuntimeError("Set JWT_SECRET to a random value of at least 32 characters (e.g. `python3 -c \"import secrets; print(secrets.token_hex(32))\"`)")
ALGORITHM = "HS256"
TOKEN_DAYS = 30
# Single sign-on with the trainer app: both apps share this cookie, its secret and the users collection.
# COOKIE_DOMAIN (e.g. chowmeinframe.com) scopes it to every subdomain; unset, it stays on the current host (local dev).
COOKIE_NAME = "nfp_session"
LEGACY_COOKIES = ["tracker_session"]
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN") or None
TRAINER_URL = os.environ.get("TRAINER_URL", "")

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== SECURITY ====================
# The same protections run in the trainer, templates and tracker apps; keep them in step.

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
                    "Content-Security-Policy": "frame-ancestors 'none'"}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
LOGIN_WINDOW = 15 * 60
LOGIN_LIMIT_PER_ACCOUNT = 10  # failed logins per window for one username from one address
LOGIN_LIMIT_PER_ADDRESS = 50  # failed logins per window from one address, any username
failed_logins: Dict[tuple, deque] = defaultdict(deque)


def same_origin(request: Request) -> bool:
    """Whether a request came from this site's own pages. The login cookie is shared with every subdomain of the
    cookie domain, so a page on a sibling subdomain counts as same-site and would get the cookie attached."""
    site = request.headers.get("sec-fetch-site")
    if site:
        return site in ("same-origin", "none")
    origin = request.headers.get("origin")
    return not origin or urlparse(origin).netloc == request.headers.get("host")


@app.middleware("http")
async def protect(request: Request, call_next):
    if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/") and not same_origin(request):
        return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def client_address(request: Request) -> str:
    # Behind Apache, trust the address it appended to X-Forwarded-For, but only when the request came from the local proxy.
    host = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[-1].strip() if forwarded and host in ("127.0.0.1", "::1") else host


def login_limits(request: Request, username: str) -> Dict[tuple, int]:
    address = client_address(request)
    return {(address, username.lower()): LOGIN_LIMIT_PER_ACCOUNT, (address,): LOGIN_LIMIT_PER_ADDRESS}


def check_login_allowed(limits: Dict[tuple, int]) -> None:
    now = datetime.now(timezone.utc).timestamp()
    for key, limit in limits.items():
        attempts = failed_logins[key]
        while attempts and now - attempts[0] > LOGIN_WINDOW:
            attempts.popleft()
        if not attempts:
            del failed_logins[key]
        elif len(attempts) >= limit:
            minutes = int((LOGIN_WINDOW - (now - attempts[0])) // 60) + 1
            raise HTTPException(status_code=429, detail=f"Too many failed logins. Try again in {minutes} minute{'s' if minutes != 1 else ''}.")


def record_failed_login(limits: Dict[tuple, int]) -> None:
    now = datetime.now(timezone.utc).timestamp()
    for key in limits:
        failed_logins[key].append(now)


def check_registration(username: str, name: str, email: str) -> None:
    if not USERNAME_PATTERN.match(username):
        raise HTTPException(status_code=400, detail="Usernames are up to 40 letters, numbers, dots, dashes or underscores")
    if len(name) > 80 or len(email) > 120:
        raise HTTPException(status_code=400, detail="Name or email is too long")


def token_revoked(payload: Dict, user: Dict) -> bool:
    """Tokens issued before the user's last password change (tokens_valid_after, epoch seconds) no longer work."""
    return payload.get("iat", 0) < user.get("tokens_valid_after", 0)

# ==================== HELPERS ====================

def create_token(username: str) -> str:
    # Same payload as the trainer app's tokens, so either app's cookie works in both.
    now = datetime.now(timezone.utc)
    return jwt.encode({"username": username, "iat": int(now.timestamp()), "exp": now + timedelta(days=TOKEN_DAYS)}, SECRET, algorithm=ALGORITHM)

def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(COOKIE_NAME, create_token(username), httponly=True, max_age=86400 * TOKEN_DAYS, samesite="lax",
                        domain=COOKIE_DOMAIN, secure=bool(COOKIE_DOMAIN))

def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        username = payload["username"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    if token_revoked(payload, user):
        raise HTTPException(status_code=401, detail="Please log in again")
    return user

# ==================== PAGES ====================

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/index.html")

@app.get("/foods", response_class=HTMLResponse)
def foods_page():
    return FileResponse("static/foods.html")

@app.get("/history", response_class=HTMLResponse)
def history_page():
    return FileResponse("static/history.html")

@app.get("/sw.js")
def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")

# ==================== AUTH ====================

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    name: str
    email: str
    password: str

@app.post("/api/login")
def login(req: LoginRequest, request: Request, response: Response):
    limits = login_limits(request, req.username.strip())
    check_login_allowed(limits)
    user = db.get_user_by_username(req.username.strip())
    if not user or not user.get("password") or not bcrypt.checkpw(req.password.encode(), user["password"].encode()):
        record_failed_login(limits)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    set_session_cookie(response, user["username"])
    return {"ok": True, "name": user.get("name", "")}

@app.post("/api/register")
def register(req: RegisterRequest, response: Response):
    # Same rules as the trainer app's register: one account works in both.
    username, name, email = req.username.strip(), req.name.strip(), req.email.strip()
    if not username or not name or not email or not req.password:
        raise HTTPException(status_code=400, detail="Please fill all fields")
    check_registration(username, name, email)
    if db.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    db.add_user({"username": username, "name": name, "email": email, "password": hashed, "role": "client"})
    set_session_cookie(response, username)
    return {"ok": True, "name": name}

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, domain=COOKIE_DOMAIN, secure=bool(COOKIE_DOMAIN), httponly=True, samesite="lax")
    for name in LEGACY_COOKIES:
        response.delete_cookie(name)
    return {"ok": True}

@app.get("/api/me")
def me(request: Request):
    user = get_current_user(request)
    return {"username": user["username"], "name": user.get("name", ""), "trainer_url": TRAINER_URL}

# ==================== FOODS ====================

@app.get("/api/foods")
def get_foods(request: Request):
    user = get_current_user(request)
    foods = db.get_foods_by_user(user["username"])
    return [{"id": str(f["_id"]), "name": f["name"], "calories": f.get("calories", 0), "protein": f.get("protein", 0), "position": f.get("position", 0)} for f in foods]

class FoodRequest(BaseModel):
    name: str
    calories: int
    protein: int

@app.post("/api/foods")
def add_food(req: FoodRequest, request: Request):
    user = get_current_user(request)
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    db.add_food(user["username"], {"name": req.name.strip()[:100], "calories": req.calories, "protein": req.protein})
    return {"ok": True}

@app.put("/api/foods/{food_id}")
def update_food(food_id: str, req: FoodRequest, request: Request):
    user = get_current_user(request)
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not db.update_food(user["username"], food_id, {"name": req.name.strip()[:100], "calories": req.calories, "protein": req.protein}):
        raise HTTPException(status_code=404, detail="Food not found")
    return {"ok": True}

@app.delete("/api/foods/{food_id}")
def delete_food(food_id: str, request: Request):
    user = get_current_user(request)
    if not db.delete_food(user["username"], food_id):
        raise HTTPException(status_code=404, detail="Food not found")
    return {"ok": True}

class PositionRequest(BaseModel):
    position: int

@app.patch("/api/foods/{food_id}/position")
def update_position(food_id: str, req: PositionRequest, request: Request):
    user = get_current_user(request)
    if not db.update_food_position(user["username"], food_id, req.position):
        raise HTTPException(status_code=404, detail="Food not found")
    return {"ok": True}

# ==================== CALORIES ====================

class EntryRequest(BaseModel):
    food_id: str | None = None
    name: str | None = None
    calories: int | None = None
    protein: int | None = None
    client_id: str | None = None

@app.get("/api/nutrition/today")
def nutrition_today(request: Request):
    user = get_current_user(request)
    midnight = datetime.combine(date.today(), time.min)
    entries = db.get_nutrition_entries_by_user_since(user["username"], midnight)
    total_calories = sum(e.get("calories", 0) for e in entries)
    total_protein = sum(e.get("protein", 0) for e in entries)
    latest_id = None
    if entries:
        latest = max(entries, key=lambda e: e.get("created_at", datetime.min))
        latest_id = str(latest["_id"])
    return {"total_calories": total_calories, "total_protein": total_protein, "latest_id": latest_id}

@app.post("/api/nutrition")
def add_nutrition(req: EntryRequest, request: Request):
    user = get_current_user(request)
    if req.food_id:
        foods = db.get_foods_by_user(user["username"])
        food = next((f for f in foods if str(f["_id"]) == req.food_id), None)
        if not food:
            raise HTTPException(status_code=404, detail="Food not found")
        food_name = food["name"]
        calories = int(food.get("calories", 0))
        protein = int(food.get("protein", 0))
    else:
        if req.calories is None and req.protein is None:
            raise HTTPException(status_code=400, detail="Provide a food_id or calories/protein")
        food_name = req.name.strip()[:100] if req.name and req.name.strip() else "Manual entry"
        calories = int(req.calories or 0)
        protein = int(req.protein or 0)
    db.add_nutrition_entry({
        "username": user["username"],
        "food_name": food_name,
        "calories": calories,
        "protein": protein,
        "created_at": datetime.now(),
        "client_id": req.client_id
    })
    return {"ok": True}

@app.delete("/api/nutrition/{entry_id}")
def delete_nutrition(entry_id: str, request: Request):
    user = get_current_user(request)
    if not db.delete_nutrition_entry(user["username"], entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}

@app.get("/api/nutrition/history")
def nutrition_history(request: Request):
    user = get_current_user(request)
    rows = db.aggregate_daily_totals(user["username"])
    return [{"date": r["_id"], "total_calories": r["total_calories"], "total_protein": r["total_protein"]} for r in rows]

