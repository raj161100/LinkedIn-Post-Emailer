import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List

from dotenv import load_dotenv
from rich import print

from gmail_helper import send_email_with_attachment
from linkedin_scraper import search_posts_with_emails, login_and_collect_emails
from resume_customizer import generate_custom_resume
from linkedin_scraper_jobs import search_jobs
from job_auto_apply import easy_apply_on_job

from cache import SeenCache

# -----------------------------
# ENV + constants
# -----------------------------
load_dotenv()  # <--- IMPORTANT: load .env once at import time

COOLDOWN_DAYS = int(os.getenv("JOB_COOLDOWN_DAYS", "10"))

# Send summary here; if REPORT_RECEIVER is not set, fall back to sender
REPORT_RECEIVER = os.getenv("REPORT_RECEIVER", "").strip()

COOLDOWN_DAYS = 10
REPORT_RECEIVER = os.getenv("REPORT_RECEIVER", "").strip()


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_env():
    load_dotenv()
    ln_email = os.getenv("LINKEDIN_EMAIL")
    ln_password = os.getenv("LINKEDIN_PASSWORD")
    sender = os.getenv("GMAIL_SENDER", "").strip()

    if not ln_email or not ln_password:
        raise SystemExit("❌ Missing LinkedIn credentials in .env")

    if not sender:
        raise SystemExit("❌ Missing GMAIL_SENDER in .env")

    return ln_email, ln_password, sender


def send_to_all(emails: List[str], sender: str, subject: str, body: str, attachment_path: str):
    sent = []
    for e in emails:
        try:
            send_email_with_attachment(
                sender=sender,
                to_addrs=[e],
                subject=subject,
                body_text=body,
                attachment_path=attachment_path,
            )
            print(f"[green]✅ Sent to {e}[/green]")
            sent.append(e)
        except Exception as ex:
            print(f"[red]❌ Failed to send {e}: {ex}[/red]")
    return sent


def load_recent_sends(cache_file: str):
    if not os.path.exists(cache_file):
        return {}
    rec = {}
    with open(cache_file, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                val = entry.get("value", "")
                parts = val.split("|")
                if len(parts) == 3:
                    email = parts[1]
                    dt = datetime.strptime(parts[2], "%Y-%m-%d")
                    rec[email] = dt
            except:
                pass
    return rec


def within_cooldown(email: str, recent: Dict[str, datetime], days=COOLDOWN_DAYS):
    if email not in recent:
        return False
    return (datetime.now() - recent[email]) < timedelta(days=days)


def load_recent_jobs(job_cache_file: str):
    if not os.path.exists(job_cache_file):
        return {}
    rec = {}
    with open(job_cache_file, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                val = entry.get("value", "")
                parts = val.split("|")
                if len(parts) == 3:
                    job_url = parts[1]
                    dt = datetime.strptime(parts[2], "%Y-%m-%d")
                    rec[job_url] = dt
            except:
                pass
    return rec


def within_job_cooldown(job_url: str, recent_jobs: Dict[str, datetime], days: int):
    if job_url not in recent_jobs:
        return False
    return (datetime.now() - recent_jobs[job_url]) < timedelta(days=days)


def get_company_name(email: str):
    try:
        return email.split("@")[1].split(".")[0].capitalize()
    except Exception:
        return "Unknown"


def append_email_log(role, keyword, emails, preferred=None, links=None):
    """
    Write one JSONL row per email.

    `links` is an optional list (same length as emails) of LinkedIn post URLs.
    """
    os.makedirs("logs", exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = f"logs/sent_{today}.jsonl"

    if links is None or len(links) != len(emails):
        links = [None] * len(emails)

    with open(log_file, "a", encoding="utf-8") as f:
        for e, link in zip(emails, links):
            log = {
                "timestamp": datetime.now().isoformat(),
                "role": role,
                "keyword": keyword,
                "email": e,
                "company": get_company_name(e),
                "preferred_bucket": preferred,
                "post_link": link,
            }
            f.write(json.dumps(log) + "\n")


def append_job_log(job_info):
    os.makedirs("logs", exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = f"logs/jobs_{today}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(job_info) + "\n")


def generate_report_body():
    """
    Summary email body – grouped by role, but de-duplicated per email
    and still works even with the new post_link field.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = f"logs/sent_{today}.jsonl"

    if not os.path.exists(log_file):
        return "No emails sent in this run."

    grouped = {}
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
            except Exception:
                continue

            e = data["email"]
            if e not in grouped:
                grouped[e] = {
                    "email": e,
                    "company": data.get("company", ""),
                    "roles": set(),
                    "keywords": set(),
                }

            grouped[e]["roles"].add(data["role"])
            grouped[e]["keywords"].add(data["keyword"])

    lines = [f"📅 Report for {today}\n"]
    lines.append(f"Total unique recruiters emailed: {len(grouped)}\n")

    for e, data in grouped.items():
        lines.append(
            f"\n• {e} ({data['company']})\n"
            f"   Roles: {', '.join(sorted(data['roles']))}\n"
            f"   Keywords: {', '.join(sorted(data['keywords']))}"
        )

    return "\n".join(lines)


def send_summary(sender: str) -> None:
    """
    Email yourself a grouped summary for today's run.

    Uses REPORT_RECEIVER from .env if present, otherwise falls back to `sender`.
    If neither is set, it logs a warning and skips sending.
    """
    try:
        # Prefer REPORT_RECEIVER, else use the Gmail sender
        recipient = (REPORT_RECEIVER or sender or "").strip()
        if not recipient:
            print(
                "[yellow]⚠ No REPORT_RECEIVER or sender configured; "
                "skipping summary email.[/yellow]"
            )
            return

        # Build the text body from today's JSONL log (your existing grouping logic)
        body = generate_report_body()
        if not body.strip():
            print(
                "[yellow]⚠ No log entries for today; "
                "skipping summary email.[/yellow]"
            )
            return

        today = datetime.utcnow().strftime("%Y-%m-%d")
        subject = f"📊 Auto Emailer Summary — {today}"

        send_email_with_attachment(
            sender=sender,
            to_addrs=[recipient],
            subject=subject,
            body_text=body,
        )
        print(f"[green]📧 Summary Email Sent to {recipient}[/green]")

    except Exception as e:
        print(f"[red]❌ Summary Email Failed: {e}[/red]")


# -----------------------------
# ASYNC CORE EXECUTION (used by dashboard)
# -----------------------------
async def run_once_async():
    cfg = load_config()
    ln_email, ln_password, sender = get_env()

    cache_file = cfg.get("cache_file", "data/seen.jsonl")
    cache = SeenCache(cache_file)
    recent = load_recent_sends(cache_file)

    job_cache_file = cfg.get("job_cache_file", "data/jobs_seen.jsonl")
    job_cache = SeenCache(job_cache_file)
    recent_jobs = load_recent_jobs(job_cache_file)
    job_cooldown_days = cfg.get("job_cooldown_days", 10)

    max_years = cfg["experience"]["max_years"]
    auto_apply_cfg = cfg.get("auto_apply", {})
    auto_apply_enabled = auto_apply_cfg.get("enabled", False)
    apply_limit = auto_apply_cfg.get("limit_per_run", 0)

    for role in cfg["roles"]:
        role_name = role["name"]
        keywords = role["keywords"]
        pages = cfg["search_pages"]

        print(f"\n[bold yellow]=== Processing Role: {role_name} ===[/bold yellow]")

        static_resume = role["resume_path"]
        customize_enabled = role["customize"]["enabled"]
        base_resume = role["customize"]["base_resume"]
        required_skills = [s.lower() for s in role.get("required_skills", [])]

        subject = role["message_subject"]
        body = role["message_body"]

        # 1) SCRAPE POSTS + EMAIL GROUPS
        posts = await search_posts_with_emails(
            ln_email, ln_password, keywords, pages, max_years
        )
        email_groups = await login_and_collect_emails(
            ln_email, ln_password, keywords, pages, max_years
        )

        # role-level de-dup
        role_seen = set()
        kw_to_emails = []
        for kw, emails in email_groups.items():
            valid_emails = []
            for e in emails:
                if within_cooldown(e, recent):
                    continue
                if cache.has(f"{role_name}|{e}"):
                    continue
                role_seen.add(e)
                valid_emails.append(e)
            kw_to_emails.append((kw, valid_emails))

        unique_new_emails = list(role_seen)

        # 2) optional tailored resume
        tailored_resume = None
        if unique_new_emails and customize_enabled and os.path.exists(base_resume):
            sample_text = ""
            company_hint = None
            for p in posts:
                if p["skipped_reason"] is None:
                    sample_text = p["text"]
                    if p["emails"]:
                        company_hint = p["emails"][0].split("@")[1].split(".")[0]
                    break
            try:
                tailored_resume = generate_custom_resume(
                    role_name=role_name,
                    base_resume_path=base_resume,
                    job_text=sample_text,
                    output_dir="assets/generated_resumes",
                    company_hint=company_hint,
                )
                print(f"[cyan]📝 Tailored resume generated: {tailored_resume}[/cyan]")
            except Exception as e:
                print(f"[yellow]⚠ Resume customization failed: {e}[/yellow]")

        resume_path = tailored_resume or static_resume

        # 3) send emails
        if not unique_new_emails:
            print("[dim]No new unique emails for this role.[/dim]")
        else:
            sent = send_to_all(unique_new_emails, sender, subject, body, resume_path)

            cache.add_all(
                [f"{role_name}|{e}|{datetime.now().strftime('%Y-%m-%d')}" for e in sent]
            )

            # best-effort preferred vs neutral + post_link
            for kw, emails_for_kw in kw_to_emails:
                pref_sent, neut_sent = [], []
                pref_links, neut_links = [], []

                for p in posts:
                    if p["keyword"] == kw and p["skipped_reason"] is None:
                        link = p.get("link")
                        post_sent = [e for e in p["emails"] if e in sent]
                        if not post_sent:
                            continue
                        if p["preferred"]:
                            pref_sent.extend(post_sent)
                            pref_links.extend([link] * len(post_sent))
                        else:
                            neut_sent.extend(post_sent)
                            neut_links.extend([link] * len(post_sent))

                if pref_sent:
                    append_email_log(
                        role_name, kw, pref_sent, preferred=True, links=pref_links
                    )
                if neut_sent:
                    append_email_log(
                        role_name, kw, neut_sent, preferred=False, links=neut_links
                    )

        # (Auto-apply block can be re-added here later if you want,
        #  using search_jobs(...) + easy_apply_on_job(...).)

    cache.close()
    job_cache.close()

    # send daily summary
    send_summary(sender)


# -----------------------------
# CLI helper for manual runs
# -----------------------------
def run_once():
    asyncio.run(run_once_async())


if __name__ == "__main__":
    run_once()
