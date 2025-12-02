# linkedin_scraper_jobs.py
# Job-search scraper for LinkedIn Auto Apply
# Features:
#   - Persistent session (linkedin_state.json)
#   - CAPTCHA / MFA manual verification
#   - Visa-aware filtering
#   - Years of experience filtering
#   - Location filtering (include + exclude)
#   - NOT-HIRING filter
#   - Extracts job title, company, location, job URL
#   - Only returns jobs that support Easy Apply (text check)

import os
import asyncio
import re
import json
from typing import List, Dict, Any
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# ---------------------------------------
# Regex + Phrases
# ---------------------------------------
EXPERIENCE_RE = re.compile(r"(\d{1,2})\s*(?:\+?\s*)?(?:years?|yrs?)", re.I)

VISA_BLOCKERS = [
    "no h1b", "usc only", "us citizen", "no sponsorship", "cannot sponsor",
    "sponsorship not available", "gc only", "must be gc",
]

NOT_HIRING_PHRASES = [
    "i am not a recruiter",
    "i'm not a recruiter",
    "not a recruiter",
    "please don't send resumes",
    "please dont send resumes",
    "don’t send resumes",
    "do not send resumes",
    "open to work",
    "looking for a job",
    "seeking opportunities",
    "actively looking for a job",
    "actively open and looking",
    "urgent job search",
]

EASY_APPLY_TEXT = "easy apply"


# ---------------------------------------
# Experience Helpers
# ---------------------------------------
def extract_years(text: str):
    m = EXPERIENCE_RE.findall(text)
    if not m:
        return None
    nums = [int(x) for x in m]
    return max(nums) if nums else None


def is_experience_ok(text: str, max_years: int):
    t = text.lower()
    if any(x in t for x in ["entry level", "junior", "graduate"]):
        return True
    yrs = extract_years(t)
    if yrs is None:
        return True
    return yrs <= max_years


# ---------------------------------------
# Location Helpers
# ---------------------------------------
def detect_location(text: str, include_locs: List[str], exclude_locs: List[str]):
    tlow = text.lower()

    for ex in exclude_locs:
        if ex in tlow:
            return "exclude", ex

    for inc in include_locs:
        if inc in tlow:
            return "include", inc

    if include_locs:
        return "not_allowed", None

    return None, None


# ---------------------------------------
# Main Job Scraper
# ---------------------------------------
async def search_jobs(
    email: str,
    password: str,
    keywords: List[str],
    max_years: int,
    pages: int = 2,
) -> List[Dict[str, Any]]:
    """
    Returns a list of job dicts:
    {
        'keyword': kw,
        'title': title,
        'company': company,
        'location': location,
        'link': job_url
    }
    """
    # Load location filters
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    include_locs = [loc.lower() for loc in cfg["location_filters"]["include"]]
    exclude_locs = [loc.lower() for loc in cfg["location_filters"]["exclude"]]

    results: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=700)
        state_path = "linkedin_state.json"

        # Load or create session
        if os.path.exists(state_path):
            print("[cyan]🔁 Using saved LinkedIn session[/cyan]")
            context = await browser.new_context(storage_state=state_path)
        else:
            print("[yellow]🧾 No saved session — logging in[/yellow]")
            context = await browser.new_context()

        page = await context.new_page()

        # Validate login state
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        url = page.url

        if "login" in url or "checkpoint" in url:
            print("[yellow]⚠ Session expired — Logging in manually[/yellow]")
            await page.goto("https://www.linkedin.com/login")
            await page.fill("#username", email)
            await page.fill("#password", password)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("domcontentloaded")

            print("[yellow]⚠ Solve CAPTCHA or verify identity in browser[/yellow]")
            input("⏸️ Press ENTER after verification to continue...")

            await context.storage_state(path=state_path)
            print("[green]💾 LinkedIn session refreshed and saved![/green]")
        else:
            print("[green]✅ Logged in with saved session[/green]")

        # ---------------------------------------
        # Begin job search
        # ---------------------------------------
        for kw in keywords:
            print(f"\n[blue]🔍 Searching jobs for:[/blue] {kw}")
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={quote(kw)}"
            await page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Scroll to load jobs
            for _ in range(pages):
                await page.mouse.wheel(0, 3500)
                await asyncio.sleep(1)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            job_cards = soup.find_all(
                "li", class_=re.compile("jobs-search-results__list-item")
            )

            for jc in job_cards:
                try:
                    title_el = jc.find("h3")
                    comp_el = jc.find("h4")
                    loc_el = jc.find("span", class_=re.compile("location"))
                    link_el = jc.find("a", href=re.compile("/jobs/view/"))

                    if not link_el:
                        continue

                    job_url = (
                        "https://www.linkedin.com"
                        + link_el["href"].split("?")[0]
                    )
                    title = title_el.get_text(strip=True) if title_el else ""
                    company = comp_el.get_text(strip=True) if comp_el else ""
                    location = loc_el.get_text(strip=True) if loc_el else ""

                    text_blob = " ".join(jc.stripped_strings).lower()

                    # NOT-HIRING / "open to work" style posts
                    if any(p in text_blob for p in NOT_HIRING_PHRASES):
                        continue

                    # Visa filter
                    if any(v in text_blob for v in VISA_BLOCKERS):
                        continue

                    # Experience filter
                    if not is_experience_ok(text_blob, max_years):
                        continue

                    # Location filter
                    loc_rule, matched = detect_location(
                        text_blob + " " + location.lower(), include_locs, exclude_locs
                    )

                    if loc_rule == "exclude":
                        continue
                    if loc_rule == "not_allowed":
                        continue

                    # Only Easy Apply jobs (best-effort via snippet text)
                    if EASY_APPLY_TEXT not in text_blob:
                        continue

                    results.append(
                        {
                            "keyword": kw,
                            "title": title,
                            "company": company,
                            "location": location,
                            "link": job_url,
                        }
                    )

                except Exception as e:
                    print(f"[red]⚠ Error parsing job: {e}[/red]")

        await browser.close()
        return results
