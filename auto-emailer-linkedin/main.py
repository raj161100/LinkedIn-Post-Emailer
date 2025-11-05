import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict
from collections import defaultdict
from dotenv import load_dotenv
from rich import print

from gmail_helper import send_email_with_attachment
from linkedin_scraper import login_and_collect_emails
from cache import SeenCache

# === CONFIG ===
COOLDOWN_DAYS = 10             # days to wait before recontacting same email
REPORT_RECEIVER = "rithwikrajmallam@gmail.com"  # daily report destination


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_env():
    """Load LinkedIn and Gmail credentials from .env"""
    load_dotenv()
    ln_email = os.getenv("LINKEDIN_EMAIL")
    ln_password = os.getenv("LINKEDIN_PASSWORD")
    sender = os.getenv("GMAIL_SENDER", "").strip()

    if not ln_email or not ln_password:
        raise SystemExit("❌ Missing LINKEDIN_EMAIL or LINKEDIN_PASSWORD in .env")
    if not sender:
        raise SystemExit("❌ Missing GMAIL_SENDER in .env")

    return ln_email, ln_password, sender


def send_to_all(emails: List[str], sender: str, subject: str, body: str, resume_path: str) -> List[str]:
    """Send email with resume attachment via Gmail API."""
    sent = []
    for e in emails:
        try:
            result = send_email_with_attachment(
                sender=sender,
                to_addrs=[e],
                subject=subject,
                body_text=body,
                attachment_path=resume_path if os.path.exists(resume_path) else None,
            )
            print(f"[green]✅ Sent to {e}[/green] (id={result.get('id')})")
            sent.append(e)
        except Exception as ex:
            print(f"[red]❌ Failed to send to {e}: {ex}[/red]")
    return sent


def load_recent_sends(cache_path: str) -> Dict[str, datetime]:
    """Read cache and return dict {email: last_date}"""
    if not os.path.exists(cache_path):
        return {}
    recent = {}
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                val = entry.get("value", "")
                parts = val.split("|")
                if len(parts) >= 3:
                    email = parts[1]
                    date_str = parts[2]
                    recent[email] = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                continue
    return recent


def within_cooldown(email: str, recent: Dict[str, datetime]) -> bool:
    """Check if an email was contacted within the cooldown window"""
    if email not in recent:
        return False
    last_sent = recent[email]
    return datetime.now() - last_sent < timedelta(days=COOLDOWN_DAYS)


def get_company_name(email: str) -> str:
    """Extract company name from recruiter email domain"""
    try:
        domain = email.split("@")[1]
        company = domain.split(".")[0].capitalize()
        return company
    except Exception:
        return "Unknown"


def append_to_daily_log(role: str, keyword: str, emails: List[str]):
    """Append sent email details to today's log file"""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(log_dir, f"sent_{today}.jsonl")

    with open(log_path, "a", encoding="utf-8") as f:
        for e in emails:
            company = get_company_name(e)
            record = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "role": role,
                "keyword": keyword,
                "email": e,
                "company": company
            }
            f.write(json.dumps(record) + "\n")


def generate_daily_report() -> str:
    """Compile a summary of today's emails"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join("logs", f"sent_{today}.jsonl")
    if not os.path.exists(log_path):
        return "No emails were sent today."

    summary = defaultdict(list)
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            summary[data["role"]].append(data)

    report_lines = [f"📅 Daily Report for {today}\n"]
    total_count = 0
    for role, entries in summary.items():
        report_lines.append(f"\n🔹 Role: {role} — {len(entries)} emails sent")
        for e in entries:
            report_lines.append(f"  • {e['email']} ({e['company']}) via '{e['keyword']}'")
            total_count += 1

    report_lines.append(f"\nTotal Emails Sent Today: {total_count}\n")
    return "\n".join(report_lines)


def send_daily_report(sender: str):
    """Send the compiled daily report via Gmail"""
    body = generate_daily_report()
    subject = f"📊 Auto Emailer Report — {datetime.now().strftime('%Y-%m-%d')}"
    try:
        send_email_with_attachment(
            sender=sender,
            to_addrs=[REPORT_RECEIVER],
            subject=subject,
            body_text=body,
        )
        print(f"[cyan]📧 Daily report sent to {REPORT_RECEIVER}[/cyan]")
    except Exception as e:
        print(f"[red]⚠️ Failed to send daily report: {e}[/red]")


def run_once():
    """Runs one full scan across all roles defined in config.json"""
    cfg = load_config()
    ln_email, ln_password, sender = get_env()
    cache_file = cfg.get("cache_file", "data/seen.jsonl")
    cache = SeenCache(cache_file)
    recent_sends = load_recent_sends(cache_file)

    for role in cfg.get("roles", []):
        role_name = role.get("name", "Unknown Role")
        keywords = role.get("keywords", [])
        pages = int(cfg.get("search_pages", 2))
        resume_path = role.get("resume_path")
        subject = role.get("message_subject")
        body = role.get("message_body")

        print(f"\n[bold yellow]=== Processing Role: {role_name} ===[/bold yellow]")
        results = asyncio.run(login_and_collect_emails(ln_email, ln_password, keywords, pages))

        for kw, emails in results.items():
            print(f"[bold]Keyword:[/bold] {kw} → found {len(emails)} emails")

            # Filter out duplicates and cooldowned addresses
            new_emails = []
            for e in emails:
                if cache.has(f"{kw}|{e}"):
                    continue
                if within_cooldown(e, recent_sends):
                    print(f"[yellow]⏳ Skipping {e} (within {COOLDOWN_DAYS}-day cooldown)[/yellow]")
                    continue
                new_emails.append(e)

            if not new_emails:
                print("[dim]No new emails to send.[/dim]")
                continue

            print(f"[cyan]New emails to send:[/cyan] {new_emails}")
            sent = send_to_all(new_emails, sender, subject, body, resume_path)

            # Record results in cache and log
            cache.add_all([f"{kw}|{e}|{datetime.now().strftime('%Y-%m-%d')}" for e in sent])
            append_to_daily_log(role_name, kw, sent)

    cache.close()
    print("\n[bold green]✅ All roles processed successfully![/bold green]")


def main():
    """Handles run_mode and looping every X minutes."""
    cfg = load_config()
    mode = cfg.get("run_mode", "loop").lower()
    interval = int(cfg.get("loop_interval_minutes", 15))
    last_report_date = datetime.now().date()

    if mode == "once":
        print("[blue]Running once mode...[/blue]")
        run_once()
        send_daily_report(get_env()[2])
    else:
        print(f"[magenta]Loop mode enabled — checking every {interval} minutes[/magenta]")
        while True:
            start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[bold]🕒 Starting scan at {start}[/bold]")
            run_once()

            # Send report at midnight or next day
            if datetime.now().date() != last_report_date:
                send_daily_report(get_env()[2])
                last_report_date = datetime.now().date()

            print(f"[dim]Sleeping for {interval} minutes before next scan...[/dim]")
            time.sleep(interval * 60)


if __name__ == "__main__":
    main()
 