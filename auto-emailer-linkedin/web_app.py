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
import asyncio
from datetime import datetime, date
from typing import List, Dict, Any
import random

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
CREDENTIALS_PATH = os.path.join(BASE_DIR, "data", "credentials.json")

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# -----------------------------
# Loop State
# -----------------------------
RUN_LOOP = False
LOOP_THREAD = None
LAST_RUN = None
RUN_ONCE_ACTIVE = False
LAST_RUN_ONCE_FINISHED = None

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


def load_credentials():
    if not os.path.exists(CREDENTIALS_PATH):
        return {}
    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_credentials(updates: Dict[str, Any]):
    current = load_credentials()
    changed = False
    for k, v in updates.items():
        if v is None or v == "":
            continue
        if current.get(k) != v:
            current[k] = v
            changed = True
    if changed:
        with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)


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
async def run_once_route(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    print(f"[RunOnce] Triggered via UI with keys: {list(payload.keys())}")

    def worker():
        global RUN_ONCE_ACTIVE, LAST_RUN_ONCE_FINISHED, LAST_RUN
        RUN_ONCE_ACTIVE = True
        try:
            asyncio.run(run_once_async(payload))
        except BaseException as exc:
            import traceback
            print("[RunOnce] ERROR:", exc)
            traceback.print_exc()
        finally:
            RUN_ONCE_ACTIVE = False
            LAST_RUN_ONCE_FINISHED = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            LAST_RUN = LAST_RUN_ONCE_FINISHED

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    global LAST_RUN
    LAST_RUN = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return RedirectResponse("/dashboard", status_code=303)


@app.post("/api/run", status_code=202)
async def api_run(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "detail": "Invalid JSON payload"}

    asyncio.create_task(run_once_async(payload))

    global LAST_RUN
    LAST_RUN = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "accepted", "received_keys": list(payload.keys())}


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
    creds = load_credentials()
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "cfg": cfg, "creds": creds},
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
    linkedin_email: str = Form(None),
    linkedin_password: str = Form(None),
    linkedin_cookie: str = Form(None),
    gmail_sender: str = Form(None),
    gmail_token: str = Form(None),
    google_client_id: str = Form(None),
    google_client_secret: str = Form(None),
    google_project_id: str = Form(None),
    google_secret_file: UploadFile = File(None),
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

    cred_updates: Dict[str, Any] = {
        "linkedin_email": linkedin_email,
        "linkedin_password": linkedin_password,
        "linkedin_cookie": linkedin_cookie,
        "gmail_sender": gmail_sender,
    }

    if gmail_token:
        try:
            cred_updates["gmail_token"] = json.loads(gmail_token)
        except Exception:
            pass  # ignore invalid JSON to avoid breaking stored creds

    # Handle Google client secret
    client_secret_path = os.path.join(BASE_DIR, "google_client_secret.json")
    existing_secret = {}
    if os.path.exists(client_secret_path):
        try:
            with open(client_secret_path, "r", encoding="utf-8") as f:
                existing_secret = json.load(f)
        except Exception:
            existing_secret = {}

    # Option 1: uploaded JSON
    if google_secret_file is not None:
        content = await google_secret_file.read()
        try:
            parsed = json.loads(content.decode("utf-8"))
            with open(client_secret_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2)
            cred_updates["google_client_id"] = parsed.get("installed", {}).get("client_id")
            cred_updates["google_client_secret"] = parsed.get("installed", {}).get("client_secret")
            cred_updates["google_project_id"] = parsed.get("installed", {}).get("project_id")
        except Exception:
            pass

    # Option 2: typed values
    elif google_client_id or google_client_secret or google_project_id:
        base_installed = existing_secret.get("installed", {})
        installed = {
            "client_id": google_client_id or base_installed.get("client_id", ""),
            "project_id": google_project_id or base_installed.get("project_id", "linkedin-auto-emailer"),
            "auth_uri": base_installed.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": base_installed.get("token_uri", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": base_installed.get(
                "auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs"
            ),
            "client_secret": google_client_secret or base_installed.get("client_secret", ""),
            "redirect_uris": base_installed.get("redirect_uris", ["http://localhost"]),
        }
        with open(client_secret_path, "w", encoding="utf-8") as f:
            json.dump({"installed": installed}, f, indent=2)
        cred_updates["google_client_id"] = installed["client_id"]
        cred_updates["google_client_secret"] = installed["client_secret"]
        cred_updates["google_project_id"] = installed["project_id"]

    save_credentials(cred_updates)

    return RedirectResponse("/settings", status_code=303)

@app.post("/delete-token")
async def delete_token():
    token_path = os.path.join(BASE_DIR, "token.json")
    if os.path.exists(token_path):
        try:
            os.remove(token_path)
        except Exception:
            pass
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
    cfg = load_config()
    return templates.TemplateResponse(
        "resumes.html",
        {"request": request, "resumes": resumes, "roles": cfg.get("roles", [])},
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


@app.post("/update-role-template")
async def update_role_template(
    role_name: str = Form(...),
    resume_filename: str = Form(None),
    message_subject: str = Form(""),
    message_body: str = Form(""),
):
    cfg = load_config()
    roles = cfg.get("roles", [])
    updated = False
    for role in roles:
        if role.get("name") == role_name:
            if resume_filename:
                role["resume_path"] = f"assets/{resume_filename}"
            if message_subject:
                role["message_subject"] = message_subject
            if message_body:
                role["message_body"] = message_body
            updated = True
            break

    if updated:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    return RedirectResponse("/resumes", status_code=303)


@app.post("/add-role")
async def add_role(
    role_name: str = Form(...),
    keywords: str = Form(""),
    required_skills: str = Form(""),
    resume_filename: str = Form(""),
    message_subject: str = Form(""),
    message_body: str = Form(""),
):
    cfg = load_config()
    cfg.setdefault("roles", [])

    def parse_csv(val: str):
        cleaned = val.replace("\n", ",")
        return [x.strip() for x in cleaned.split(",") if x.strip()]

    role = {
        "name": role_name.strip(),
        "keywords": parse_csv(keywords),
        "resume_path": f"assets/{resume_filename}" if resume_filename else "assets/PLACEHOLDER_RESUME.docx",
        "message_subject": message_subject or f"Application: {role_name}",
        "message_body": message_body
        or "Hello,\n\nI saw your post and am interested. Please find my resume attached.\n\nThank you,\n<Your Name>",
        "customize": {"enabled": False},
        "required_skills": parse_csv(required_skills),
    }

    cfg["roles"].append(role)

    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

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


@app.get("/run-status")
async def run_status():
    return {
        "running": RUN_ONCE_ACTIVE,
        "last_finished": LAST_RUN_ONCE_FINISHED,
        "last_run": LAST_RUN,
    }


# ---------- SECRET / EASTER EGG ----------
@app.get("/raj-secret", response_class=HTMLResponse)
async def raj_secret(request: Request):
    quotes = [
        "Keep grinding. Today’s DM becomes tomorrow’s offer.",
        "Ship fast, learn faster. One more email, one more win.",
        "If it scares you, it’s probably worth doing.",
        "Consistency beats intensity. Send one more outreach.",
        "Nothing changes if nothing changes. Push the next build.",
    ]
    return templates.TemplateResponse(
        "secret.html",
        {
            "request": request,
            "quote": random.choice(quotes),
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
