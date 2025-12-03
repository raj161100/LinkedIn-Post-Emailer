# linkedin_scraper.py
# Visa-aware + experience-aware LinkedIn post scanner with location + "not hiring" filters.
# Uses Playwright to load pages, BeautifulSoup to parse content.
#
# Exposes:
#   - search_posts_with_emails(...)
#   - login_and_collect_emails(...)

import os
import asyncio
import json
import random
import re
from typing import List, Dict, Any
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page

# ---------------------------
# Regex + phrases
# ---------------------------
POST_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.I)

DEFAULT_EXCLUDE_PHRASES = [
    "no h1b",
    "no h-1b",
    "us citizen",
    "usc only",
    "usc and gc only",
    "no sponsorship",
    "cannot sponsor",
    "sponsorship not available",
    "gc only",
    "only gc",
    "must be gc",
    "us only",
    "us persons only",
    "citizens only",
    "no visa",
    "no cpt",
    "no opt",
]

DEFAULT_PREFER_PHRASES = [
    "h1b ok",
    "h1b accepted",
    "h-1b ok",
    "visa sponsorship",
    "sponsorship available",
    "open to h1b",
    "can sponsor",
    "h1b welcome",
    "h1b transfer",
    "visa supported",
    "will sponsor",
    "h1b candidates",
    "provides sponsorship",
]

DEFAULT_VISA_EXCLUDE = [
    "no h1b",
    "no h-1b",
    "no sponsorship",
    "cannot sponsor",
    "sponsorship not available",
    "no visa",
    "no cpt",
    "no opt",
    "no stem opt",
    "usc & gc",
    "usc gc",
    "usc & gc only",
    "usc gc only",
]

DEFAULT_VISA_PREFER = [
    "opt",
    "stem opt",
    "cpt",
    "h1b",
    "h1-b",
    "visa sponsorship",
    "can sponsor",
    "will sponsor",
]

DEFAULT_ENTRY_TERMS = ["entry level", "junior", "graduate", "intern"]

# posts you *don't* want to email (job seekers / "open to work" etc.)
NOT_HIRING_PHRASES = [
    "i am not a recruiter",
    "i'm not a recruiter",
    "not a recruiter",
    "please don't send resumes",
    "please dont send resumes",
    "don't send resumes",
    "do not send resumes",
    "open to work",
    "looking for a job",
    "seeking opportunities",
    "actively looking for a job",
    "actively open and looking",
    "urgent job search",
]


# ---------------------------
# Experience helpers
# ---------------------------
def extract_years_of_experience(text: str):
    # 1) Standard "X years/yrs" patterns
    matches = re.findall(r"(\d{1,2})\s*(?:\+?\s*)?(?:years?|yrs?)", text, re.I)
    if matches:
        nums = [int(x) for x in matches]
        return max(nums) if nums else None

    # 2) "experience: 12+" patterns without the word years
    m = re.search(r"experience[^0-9]{0,6}(\d{1,2})\s*\+?", text, re.I)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None

    return None


def is_experience_allowed(
    text: str, max_years: int = 5, entry_terms: List[str] = None
) -> bool:
    if entry_terms is None:
        entry_terms = DEFAULT_ENTRY_TERMS

    t = text.lower()
    if any(p in t for p in entry_terms):
        return True
    yrs = extract_years_of_experience(t)
    if yrs is None:
        return True
    return yrs <= max_years


# ---------------------------
# Location helpers
# ---------------------------
def detect_location_rule(
    text: str, include_locs: List[str], exclude_locs: List[str]
):
    """
    Returns:
      ("exclude", loc)     -> explicitly excluded
      ("include", loc)     -> explicitly included
      ("not_allowed", None)-> include list exists but none matched
      (None, None)         -> no decision
    """
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


# ---------------------------
# Login helper
# ---------------------------
async def _ensure_logged_in(page: Page, email: str, password: str):
    """Ensure we are logged into LinkedIn; reuse or create session."""
    await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    url = page.url.lower()

    if "login" not in url and "checkpoint" not in url:
        print("Already logged in - using existing session")
        return

    print("[yellow]Session invalid - logging in manually[/yellow]")
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

    await page.fill('input[id="username"]', email)
    await page.fill('input[id="password"]', password)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(3)

    # If there's captcha / MFA, give user time to solve it
    current = page.url.lower()
    if "checkpoint" in current or "challenge" in current:
        print("[yellow]Solve CAPTCHA / verification in the browser window.[/yellow]")
        input("Press ENTER here after you reach your LinkedIn feed... ")

    print("[green]Logged into LinkedIn.[/green]")


# ---------------------------
# Per-keyword search
# ---------------------------
async def _search_keyword(
    page: Page,
    keyword: str,
    pages: int,
    max_years: int,
    include_locs: List[str],
    exclude_locs: List[str],
    exclude_phrases: List[str],
    prefer_phrases: List[str],
    visa_exclude: List[str],
    visa_prefer: List[str],
    entry_terms: List[str],
) -> List[Dict[str, Any]]:
    search_url = (
        f"https://www.linkedin.com/search/results/content/"
        f"?keywords={quote(keyword)}&origin=GLOBAL_SEARCH_HEADER"
    )
    print(f"[blue]Navigating to:[/blue] {search_url}")

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"[red]❌ Failed to load search for '{keyword}': {e}[/red]")
        return []

    # scroll a bit to load results
    for _ in range(pages):
        await page.wait_for_timeout(1500 + random.randint(0, 400))
        await page.mouse.wheel(0, 3500)

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # keeping it broad: any <div> could contain a post body
    divs = soup.find_all("div")

    posts: List[Dict[str, Any]] = []
    for d in divs:
        text = d.get_text(" ", strip=True)
        if not text or len(text) < 40:
            continue

        low = text.lower()
        skipped_reason = None
        preferred = False
        matched_loc = None

        # not-hiring (job seekers / "open to work") filter
        if any(p in low for p in NOT_HIRING_PHRASES):
            skipped_reason = "not_hiring"

        # visa filter
        if skipped_reason is None and any(ph in low for ph in visa_exclude):
            skipped_reason = "visa_excluded"

        # experience filter
        if skipped_reason is None and not is_experience_allowed(
            low, max_years=max_years, entry_terms=entry_terms
        ):
            skipped_reason = "experience_excluded"

        # location filter
        if skipped_reason is None:
            rule, loc = detect_location_rule(low, include_locs, exclude_locs)
            if rule == "exclude":
                skipped_reason = f"location_excluded:{loc}"
                matched_loc = loc
            elif rule == "not_allowed":
                skipped_reason = "location_not_allowed"
            elif rule == "include":
                matched_loc = loc

        # phrase exclusion (non-visa)
        if skipped_reason is None and any(ph in low for ph in exclude_phrases):
            skipped_reason = "phrase_excluded"

        # preferred phrases (if still not skipped)
        if skipped_reason is None and (
            any(ph in low for ph in prefer_phrases)
            or any(ph in low for ph in visa_prefer)
        ):
            preferred = True

        # extract emails
        emails = list({e for e in POST_EMAIL_RE.findall(low)})
        if not emails:
            continue

        # best-effort post link: prefer activity/feed/post URLs and ignore mailto/profile anchors
        post_candidates = []
        for a in d.find_all("a", href=True):
            href_clean = a["href"].split("?")[0]
            if href_clean.startswith("/"):
                href_clean = "https://www.linkedin.com" + href_clean

            # skip obvious non-post links
            if href_clean.startswith("mailto:"):
                continue

            # accept only if it looks like an activity/post/update
            if any(
                marker in href_clean
                for marker in (
                    "linkedin.com/feed/update",
                    "linkedin.com/posts/",
                    "linkedin.com/pulse/",
                    "urn:li:activity",
                )
            ):
                post_candidates.append(href_clean)

        link = post_candidates[0] if post_candidates else None

        posts.append(
            {
                "keyword": keyword,
                "text": text[:2000],
                "preferred": preferred,
                "skipped_reason": skipped_reason,
                "emails": emails,
                "location": matched_loc,
                "link": link,
            }
        )

    # logging counts for this keyword
    preferred_count = sum(
        1 for p in posts if p["preferred"] and p["skipped_reason"] is None
    )
    neutral_count = sum(
        1 for p in posts if not p["preferred"] and p["skipped_reason"] is None
    )
    skipped_count = sum(1 for p in posts if p["skipped_reason"] is not None)

    print(
        f"[cyan]Keyword:[/cyan] {keyword} - "
        f"{preferred_count} preferred, {neutral_count} neutral, {skipped_count} skipped"
    )

    return posts


# ---------------------------
# Main posts search
# ---------------------------
async def search_posts_with_emails(
    ln_email: str,
    ln_password: str,
    keywords: List[str],
    pages: int,
    max_years: int,
) -> List[Dict[str, Any]]:
    # filters from config.json (optional)
    include_locs: List[str] = []
    exclude_locs: List[str] = []
    prefer_phrases = DEFAULT_PREFER_PHRASES
    exclude_phrases = DEFAULT_EXCLUDE_PHRASES
    visa_prefer = DEFAULT_VISA_PREFER
    visa_exclude = DEFAULT_VISA_EXCLUDE
    entry_terms = DEFAULT_ENTRY_TERMS

    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
            loc_cfg = cfg.get("location_filters", {})
            include_locs = [x.lower() for x in loc_cfg.get("include", [])]
            exclude_locs = [x.lower() for x in loc_cfg.get("exclude", [])]

            ph_cfg = cfg.get("phrase_filters", {})
            prefer_phrases = [x.lower() for x in ph_cfg.get("prefer", DEFAULT_PREFER_PHRASES)]
            exclude_phrases = [x.lower() for x in ph_cfg.get("exclude", DEFAULT_EXCLUDE_PHRASES)]

            visa_cfg = cfg.get("visa_filters", {})
            visa_prefer = [x.lower() for x in visa_cfg.get("prefer", DEFAULT_VISA_PREFER)]
            visa_exclude = [x.lower() for x in visa_cfg.get("exclude", DEFAULT_VISA_EXCLUDE)]

            entry_terms = [
                x.lower() for x in cfg.get("experience", {}).get("entry_terms", DEFAULT_ENTRY_TERMS)
            ]
        except Exception as e:
            print(f"[yellow]Warning: failed to load filters from config.json: {e}[/yellow]")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=700)

        state_path = "linkedin_state.json"
        if os.path.exists(state_path):
            print("[cyan]Reusing saved LinkedIn session...[/cyan]")
            context = await browser.new_context(storage_state=state_path)
        else:
            print("[yellow]No saved session file - will login and save one.[/yellow]")
            context = await browser.new_context()

        page = await context.new_page()
        await _ensure_logged_in(page, ln_email, ln_password)

        # Save session if we just logged in
        try:
            await context.storage_state(path=state_path)
        except Exception:
            pass

        all_posts: List[Dict[str, Any]] = []
        for kw in keywords:
            try:
                items = await _search_keyword(
                    page,
                    kw,
                    pages,
                    max_years,
                    include_locs,
                    exclude_locs,
                    exclude_phrases,
                    prefer_phrases,
                    visa_exclude,
                    visa_prefer,
                    entry_terms,
                )
                all_posts.extend(items)
            except Exception as e:
                print(f"[red]❌ Error while searching for '{kw}': {e}[/red]")

        await browser.close()
        return all_posts


# ---------------------------
# Backwards-compatible aggregator
# ---------------------------
async def login_and_collect_emails(
    ln_email: str,
    ln_password: str,
    keywords: List[str],
    pages: int,
    max_years: int = 5,
) -> Dict[str, List[str]]:
    """
    Returns { keyword: [emails...] } for posts passing filters,
    with preferred posts' emails first.
    """
    posts = await search_posts_with_emails(
        ln_email, ln_password, keywords, pages, max_years
    )

    grouped: Dict[str, Dict[str, List[str]]] = {}
    for p in posts:
        if p["skipped_reason"] is not None:
            continue

        kw = p["keyword"]
        grouped.setdefault(kw, {"pref": [], "neut": []})

        bucket = "pref" if p["preferred"] else "neut"
        for e in p["emails"]:
            if e not in grouped[kw][bucket]:
                grouped[kw][bucket].append(e)

    out: Dict[str, List[str]] = {}
    for kw, buckets in grouped.items():
        ordered: List[str] = []
        seen = set()
        for bucket in ("pref", "neut"):
            for e in buckets[bucket]:
                if e not in seen:
                    ordered.append(e)
                    seen.add(e)
        out[kw] = ordered

    return out
