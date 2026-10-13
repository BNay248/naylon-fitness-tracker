from fastapi import FastAPI, Request, Response, Cookie, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date, time, timedelta, timezone
from db_manager import TrainerDB
from pydantic import BaseModel
from jose import jwt, JWTError
import bcrypt
import os

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

# ==================== HELPERS ====================

def create_token(username: str) -> str:
    # Same payload as the trainer app's tokens, so either app's cookie works in both.
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"username": username, "exp": expire}, SECRET, algorithm=ALGORITHM)

def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(COOKIE_NAME, create_token(username), httponly=True, max_age=86400 * TOKEN_DAYS, samesite="lax",
                        domain=COOKIE_DOMAIN, secure=bool(COOKIE_DOMAIN))

def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        username = jwt.decode(token, SECRET, algorithms=[ALGORITHM])["username"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
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
def login(req: LoginRequest, response: Response):
    user = db.get_user_by_username(req.username.strip())
    if not user or not user.get("password") or not bcrypt.checkpw(req.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    set_session_cookie(response, user["username"])
    return {"ok": True, "name": user.get("name", "")}

@app.post("/api/register")
def register(req: RegisterRequest, response: Response):
    # Same rules as the trainer app's register: one account works in both.
    username, name, email = req.username.strip(), req.name.strip(), req.email.strip()
    if not username or not name or not email or not req.password:
        raise HTTPException(status_code=400, detail="Please fill all fields")
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
    db.add_food(user["username"], {"name": req.name, "calories": req.calories, "protein": req.protein})
    return {"ok": True}

@app.put("/api/foods/{food_id}")
def update_food(food_id: str, req: FoodRequest, request: Request):
    user = get_current_user(request)
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not db.update_food(user["username"], food_id, {"name": req.name.strip(), "calories": req.calories, "protein": req.protein}):
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
        food_name = req.name.strip() if req.name and req.name.strip() else "Manual entry"
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

