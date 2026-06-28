from fastapi import FastAPI, Request, Response, Cookie, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date, time, timedelta
from db_manager import TrainerDB
from pydantic import BaseModel
from jose import jwt, JWTError
import bcrypt
import os

app = FastAPI()
db = TrainerDB()

SECRET = os.environ.get("JWT_SECRET", "change-this-to-something-random")
ALGORITHM = "HS256"
COOKIE_NAME = "tracker_session"

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== HELPERS ====================

def create_token(username: str, name: str) -> str:
    expire = datetime.utcnow() + timedelta(days=30)
    return jwt.encode({"username": username, "name": name, "exp": expire}, SECRET, algorithm=ALGORITHM)

def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

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
    user = db.get_user_by_username(req.username)
    if not user or not bcrypt.checkpw(req.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(req.username, user.get("name", ""))
    response.set_cookie(COOKIE_NAME, token, httponly=True, max_age=86400*30, samesite="lax")
    return {"ok": True, "name": user.get("name", "")}

@app.post("/api/register")
def register(req: RegisterRequest, response: Response):
    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    db.add_user({"username": req.username, "name": req.name, "email": req.email, "password": hashed})
    token = create_token(req.username, req.name)
    response.set_cookie(COOKIE_NAME, token, httponly=True, max_age=86400*30, samesite="lax")
    return {"ok": True, "name": req.name}

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}

@app.get("/api/me")
def me(request: Request):
    user = get_current_user(request)
    return {"username": user["username"], "name": user["name"]}

# ==================== FOODS ====================

@app.get("/api/foods")
def get_foods(request: Request):
    user = get_current_user(request)
    foods = db.get_foods_by_user(user["username"])
    return [{"id": str(f["_id"]), "name": f["name"], "calories": f.get("calories", 0), "position": f.get("position", 0)} for f in foods]

class FoodRequest(BaseModel):
    name: str
    calories: int

@app.post("/api/foods")
def add_food(req: FoodRequest, request: Request):
    user = get_current_user(request)
    db.add_food(user["username"], {"name": req.name, "calories": req.calories})
    return {"ok": True}

@app.delete("/api/foods/{food_id}")
def delete_food(food_id: str, request: Request):
    get_current_user(request)
    db.delete_food(food_id)
    return {"ok": True}

class PositionRequest(BaseModel):
    position: int

@app.patch("/api/foods/{food_id}/position")
def update_position(food_id: str, req: PositionRequest, request: Request):
    get_current_user(request)
    db.update_food_position(food_id, req.position)
    return {"ok": True}

# ==================== CALORIES ====================

class EntryRequest(BaseModel):
    food_id: str

@app.get("/api/calories/today")
def calories_today(request: Request):
    user = get_current_user(request)
    midnight = datetime.combine(date.today(), time.min)
    entries = db.get_calorie_entries_by_user_since(user["username"], midnight)
    total = sum(e.get("calories", 0) for e in entries)
    latest_id = None
    if entries:
        latest = max(entries, key=lambda e: e.get("created_at", datetime.min))
        latest_id = str(latest["_id"])
    return {"total": total, "latest_id": latest_id}

@app.post("/api/calories")
def add_calorie(req: EntryRequest, request: Request):
    user = get_current_user(request)
    foods = db.get_foods_by_user(user["username"])
    food = next((f for f in foods if str(f["_id"]) == req.food_id), None)
    if not food:
        raise HTTPException(status_code=404, detail="Food not found")
    db.add_calorie_entry({
        "username": user["username"],
        "food_name": food["name"],
        "calories": int(food.get("calories", 0)),
        "created_at": datetime.now()
    })
    return {"ok": True}

@app.delete("/api/calories/{entry_id}")
def delete_calorie(entry_id: str, request: Request):
    get_current_user(request)
    db.delete_calorie_entry(entry_id)
    return {"ok": True}

@app.get("/api/calories/history")
def calorie_history(request: Request):
    user = get_current_user(request)
    rows = db.aggregate_daily_totals(user["username"])
    return [{"date": r["_id"], "calories": r["total"]} for r in rows]