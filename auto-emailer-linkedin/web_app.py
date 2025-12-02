# web_app.py
#
# Local dashboard for RajAI LinkedIn Auto Emailer
# Fully compatible with your existing templates:
#   - settings.html expects: cfg
#   - logs.html expects: entries
#   - resumes.html expects: resumes
#   - creator.html/account.html expects: user
#   - dashboard.html expects: stats, recent, config
#
# Run using:
#   uvicorn web_app:app --reload

import os
import json
import threading
import time
from datetime import datetime, date
from typing import List, Dict, Any

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Import both sync + async entrypoints
from main import run_once, run_once_async, load_config

import subprocess
import sys

def start_loop(interval_minutes: int):
    global RUN_LOOP, LOOP_PROCESS

    if RUN_LOOP:
        return
    
    RUN_LOOP = True

    # run the worker as another Python process
    LOOP_PROCESS = subprocess.Popen(
        [sys.executable, "run_loop_worker.py", str(interval_minutes)]
    )


# -----------------------------
# SETUP
# -----------------------------
load_dotenv()

app = FastAPI(title="RajAI Auto Emailer Dashboard")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# -----------------------------
# Loop State
# -----------------------------
RUN_LOOP = False
LOOP_THREAD = None
LAST_RUN = None

def get_today_log_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOGS_DIR, f"sent_{today}.jsonl")

def _loop_worker(interval: int):
    """Runs in a background thread. Safe to call sync run_once()."""
    global RUN_LOOP, LAST_RUN
    while RUN_LOOP:
        try:
            run_once()
            LAST_RUN = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"[Loop Error] {e}")
        # sleep in 1s chunks so stop reacts quickly
        for _ in range(interval * 60):
            if not RUN_LOOP:
                break
            time.sleep(1)


def start_loop(interval: int):
    global RUN_LOOP, LOOP_THREAD
    if RUN_LOOP:
        return
    RUN_LOOP = True
    LOOP_THREAD = threading.Thread(target=_loop_worker, args=(interval,), daemon=True)
    LOOP_THREAD.start()


def stop_loop():
    global RUN_LOOP
    RUN_LOOP = False


def update_env_file(path: str, updates: Dict[str, str]):
    """
    Update or append env keys while preserving other lines/comments.
    """
    lines = []
    seen = set()

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for raw in f.readlines():
                line = raw.rstrip("\n")
                stripped = line.strip()

                if not stripped or stripped.startswith("#") or "=" not in line:
                    lines.append(line)
                    continue

                key, _ = line.split("=", 1)
                if key in updates and updates[key] is not None:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                else:
                    lines.append(line)

    for k, v in updates.items():
        if v is not None and k not in seen:
            lines.append(f"{k}={v}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# -----------------------------
# Helper Functions
# -----------------------------
def today_log_file():
    today = date.today().strftime("%Y-%m-%d")
    return os.path.join(LOGS_DIR, f"sent_{today}.jsonl")


def read_recent_emails(limit: int = 20):
    path = get_today_log_file()
    if not os.path.exists(path):
        return []

    raw_items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                raw_items.append(json.loads(line))
            except Exception:
                pass

    # group by email, but keep role/keyword detail as comma-joined lists
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in raw_items:
        email = item.get("email", "")
        if not email:
            continue
        if email not in grouped:
            grouped[email] = {
                "email": email,
                "company": item.get("company", ""),
                "timestamp": item.get("timestamp", ""),
                "roles": set(),
                "keywords": set(),
                "preferred_bucket": item.get("preferred_bucket"),
                "post_link": item.get("post_link", ""),
            }

        grouped[email]["roles"].add(item.get("role", ""))
        grouped[email]["keywords"].add(item.get("keyword", ""))

        # keep the most recent timestamp/post link encountered
        if item.get("timestamp", "") > grouped[email]["timestamp"]:
            grouped[email]["timestamp"] = item.get("timestamp", "")
            grouped[email]["company"] = item.get("company", "")
            grouped[email]["post_link"] = item.get("post_link", "")

        # prefer True > False > None for preferred_bucket if mixed
        current_pref = grouped[email]["preferred_bucket"]
        new_pref = item.get("preferred_bucket")
        if current_pref is None or (new_pref is True and current_pref is not True):
            grouped[email]["preferred_bucket"] = new_pref

    # flatten sets to comma-joined strings
    entries = []
    for e, data in grouped.items():
        entries.append({
            "email": e,
            "company": data["company"],
            "timestamp": data["timestamp"],
            "role": ", ".join(sorted(r for r in data["roles"] if r)),
            "keyword": ", ".join(sorted(k for k in data["keywords"] if k)),
            "preferred_bucket": data["preferred_bucket"],
            "post_link": data["post_link"],
        })

    # Sort newest -> oldest
    entries.sort(key=lambda x: x["timestamp"], reverse=True)

    return entries[:limit]



def compute_stats() -> Dict[str, Any]:
    cfg = load_config()
    emails = read_recent_emails(limit=5000)
    return {
        "emails_sent": len(emails),
        "active_roles": len(cfg.get("roles", [])),
        "loop_status": "RUNNING" if RUN_LOOP else "STOPPED",
        "last_run": LAST_RUN,
        "loop_interval": cfg.get("loop_interval_minutes", 120),
    }


def list_resumes() -> List[str]:
    out: List[str] = []
    for f in os.listdir(ASSETS_DIR):
        if f.lower().endswith((".doc", ".docx", ".pdf")):
            out.append(f)
    return sorted(out)


# -----------------------------
# Routes
# -----------------------------
@app.get("/", include_in_schema=False)
async def home():
    # keep old behavior: dashboard at /dashboard
    return RedirectResponse("/dashboard")


# ---------- DASHBOARD ----------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    cfg = load_config()
    stats = compute_stats()
    recent = read_recent_emails(limit=20)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "recent": recent,
            "config": cfg,
        },
    )


# ---------- RUN PIPELINE ----------
@app.post("/run-once")
async def run_once_route():
    def worker():
        import asyncio
        asyncio.run(run_once_async())

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    global LAST_RUN
    LAST_RUN = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return RedirectResponse("/dashboard", status_code=303)



@app.post("/loop/start")
async def start_loop_route():
    cfg = load_config()
    interval = cfg.get("loop_interval_minutes", 120)
    start_loop(interval)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/loop/stop")
async def stop_loop_route():
    stop_loop()
    return RedirectResponse("/dashboard", status_code=303)


# ---------- SETTINGS ----------
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    cfg = load_config()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "cfg": cfg},
    )


@app.post("/update-settings")
async def update_settings(
    auto_apply: str = Form(None),
    limit_per_run: str = Form(None),
    max_years: str = Form(None),
    include_locs: str = Form(""),
    exclude_locs: str = Form(""),
    loop_interval: str = Form(None),
    prefer_phrases: str = Form(""),
    exclude_phrases: str = Form(""),
    visa_prefer: str = Form(""),
    visa_exclude: str = Form(""),
    entry_terms: str = Form(""),
):
    cfg = load_config()

    def to_int(val, default):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def parse_csv(val: str):
        cleaned = val.replace("\n", ",")
        return [x.strip() for x in cleaned.split(",") if x.strip()]

    cfg.setdefault("auto_apply", {})
    cfg.setdefault("experience", {})
    cfg.setdefault("location_filters", {})
    cfg.setdefault("phrase_filters", {})
    cfg.setdefault("visa_filters", {})

    cfg["auto_apply"]["enabled"] = auto_apply is not None
    cfg["auto_apply"]["limit_per_run"] = to_int(
        limit_per_run, cfg["auto_apply"].get("limit_per_run", 5)
    )

    cfg["experience"]["max_years"] = to_int(
        max_years, cfg["experience"].get("max_years", 5)
    )

    cfg["location_filters"]["include"] = parse_csv(include_locs)
    cfg["location_filters"]["exclude"] = parse_csv(exclude_locs)

    cfg["loop_interval_minutes"] = to_int(
        loop_interval, cfg.get("loop_interval_minutes", 120)
    )

    cfg["phrase_filters"]["prefer"] = parse_csv(prefer_phrases)
    cfg["phrase_filters"]["exclude"] = parse_csv(exclude_phrases)
    cfg["visa_filters"]["prefer"] = parse_csv(visa_prefer)
    cfg["visa_filters"]["exclude"] = parse_csv(visa_exclude)
    cfg["experience"]["entry_terms"] = parse_csv(entry_terms)

    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    return RedirectResponse("/settings", status_code=303)

# ---------- LOGS ----------
@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    rows = read_recent_emails(limit=1000)
    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "entries": rows,  # logs.html expects 'entries'
        },
    )


# ---------- RESUMES ----------
@app.get("/resumes", response_class=HTMLResponse)
async def resumes_page(request: Request):
    resumes = list_resumes()
    return templates.TemplateResponse(
        "resumes.html",
        {"request": request, "resumes": resumes},
    )


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    dest = os.path.join(ASSETS_DIR, file.filename)
    with open(dest, "wb") as f:
        f.write(await file.read())
    return RedirectResponse("/resumes", status_code=303)


@app.post("/delete-resume")
async def delete_resume(filename: str = Form(...)):
    path = os.path.join(ASSETS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
    return RedirectResponse("/resumes", status_code=303)


# ---------- ACCOUNT ----------
@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    # Show current env values (password intentionally omitted)
    env_data = {
        "linkedin_email": os.getenv("LINKEDIN_EMAIL", ""),
        "gmail_sender": os.getenv("GMAIL_SENDER", ""),
    }

    return templates.TemplateResponse(
        "creator.html",
        {
            "request": request,
            "user": {
                "name": "Raj",
                "email": "rithwikrajmallam@gmail.com",
                "role": "Creator",
                "created_at": "2025-07-11",
            },
            "env": env_data,
        },
    )


@app.post("/account")
async def update_account(
    google_client_secret: UploadFile = File(None),
    linkedin_email: str = Form(None),
    linkedin_password: str = Form(None),
    gmail_sender: str = Form(None),
):
    env_path = os.path.join(BASE_DIR, ".env")
    updates = {
        "LINKEDIN_EMAIL": linkedin_email,
        "LINKEDIN_PASSWORD": linkedin_password,
        "GMAIL_SENDER": gmail_sender,
    }

    # Write env values if provided
    if any(v is not None and v != "" for v in updates.values()):
        update_env_file(env_path, updates)
        load_dotenv(override=True)

    # Save Google client secret file if uploaded
    if google_client_secret is not None:
        dest = os.path.join(BASE_DIR, "google_client_secret.json")
        with open(dest, "wb") as f:
            f.write(await google_client_secret.read())

    return RedirectResponse("/account", status_code=303)


# ---------- HEALTH ----------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "loop": RUN_LOOP,
        "last_run": LAST_RUN,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
