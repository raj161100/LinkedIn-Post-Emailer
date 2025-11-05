import asyncio
import re
import random
from urllib.parse import quote
from typing import List, Dict

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

POST_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.I)


async def fetch_emails_for_keyword(page, keyword: str, pages: int = 2) -> Dict[str, List[str]]:
    """
    Search LinkedIn posts for the given keyword.
    Extract recruiter emails while:
      - Skipping posts that mention non-sponsorship keywords (e.g., No H1B)
      - Prioritizing posts that mention sponsorship-friendly terms (e.g., H1B OK)
    """
    found_preferred = set()
    found_neutral = set()
    found_skipped = 0

    search_url = f"https://www.linkedin.com/search/results/content/?keywords={quote(keyword)}&origin=CLUSTER_EXPANSION"
    await page.goto(search_url, wait_until="domcontentloaded")

    # --- Define filtering keywords ---
    exclude_phrases = [
        "no h1b", "no h-1b", "us citizen", "usc only", "usc and gc only",
        "no sponsorship", "cannot sponsor", "sponsorship not available",
        "gc only", "only gc", "must be gc", "us only", "us persons only",
        "citizens only", "no visa", "no cpt", "no opt"
    ]

    prefer_phrases = [
        "h1b ok", "h1b accepted", "h-1b ok", "visa sponsorship", "sponsorship available",
        "open to h1b", "can sponsor", "h1b welcome", "h1b transfer", "visa supported",
        "will sponsor", "h1b candidates", "provides sponsorship"
    ]

    # Scroll and load multiple pages
    for _ in range(pages):
        await page.wait_for_timeout(1500 + random.randint(0, 400))
        await page.mouse.wheel(0, 3500)

    html = await page.content()
    soup = BeautifulSoup(html, "html5lib")
    posts = soup.find_all("div")

    for post in posts:
        text = post.get_text(" ", strip=True).lower()

        # Exclude posts that clearly reject sponsorship
        if any(phrase in text for phrase in exclude_phrases):
            found_skipped += 1
            continue

        # Prefer posts that mention H1B / sponsorship friendly terms
        if any(phrase in text for phrase in prefer_phrases):
            for e in POST_EMAIL_RE.findall(text):
                found_preferred.add(e)
            continue

        # Neutral posts (no mention either way)
        for e in POST_EMAIL_RE.findall(text):
            found_neutral.add(e)

    # Logging stats
    print(f"[cyan]Keyword:[/cyan] {keyword} → {len(found_preferred)} preferred, "
          f"{len(found_neutral)} neutral, {found_skipped} skipped")

    # Combine preferred first, then neutral
    ordered_emails = list(found_preferred) + list(found_neutral)
    return {"preferred": sorted(list(found_preferred)),
            "neutral": sorted(list(found_neutral)),
            "skipped_count": found_skipped,
            "all": ordered_emails}


async def login_and_collect_emails(email: str, password: str, keywords: List[str], pages: int) -> Dict[str, List[str]]:
    """Logs into LinkedIn once and collects recruiter emails for all given keywords."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # --- Login ---
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await page.fill('input[id="username"]', email)
        await page.fill('input[id="password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        results = {}
        for kw in keywords:
            print(f"\n[bold yellow]🔍 Searching posts for keyword:[/bold yellow] {kw}")
            try:
                emails_data = await fetch_emails_for_keyword(page, kw, pages=pages)
                results[kw] = emails_data["all"]
            except Exception as e:
                print(f"[red]⚠️ Error while fetching for {kw}: {e}[/red]")
                results[kw] = []

        await browser.close()
        return results
