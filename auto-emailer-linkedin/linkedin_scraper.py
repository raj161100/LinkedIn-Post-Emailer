
import asyncio
import os
import re
from typing import List, Dict
from urllib.parse import quote

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import time
import random

POST_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.I)

# Basic heuristics to get visible text from a LinkedIn search page
def extract_emails_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html5lib")
    # Focus on feed posts and result containers
    texts = []
    for tag in soup.find_all(["div", "span", "p", "li", "a"]):
        s = tag.get_text(" ", strip=True)
        if s:
            texts.append(s)
    blob = " ".join(texts)
    return list({e for e in POST_EMAIL_RE.findall(blob)})

async def fetch_emails_for_keyword(page, keyword: str, pages: int = 2) -> List[str]:
    found = set()
    search_url = f"https://www.linkedin.com/search/results/content/?keywords={quote(keyword)}&origin=CLUSTER_EXPANSION"
    await page.goto(search_url, wait_until="domcontentloaded")
    # Scroll a few times to load more items
    for _ in range(pages):
        await page.wait_for_timeout(1500 + random.randint(0, 600))
        await page.mouse.wheel(0, 3000)
    html = await page.content()
    emails = extract_emails_from_html(html)
    for e in emails:
        found.add(e)
    return sorted(found)

async def login_and_collect_emails(email: str, password: str, keywords: List[str], pages: int) -> Dict[str, List[str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await page.fill('input[id="username"]', email)
        await page.fill('input[id="password"]', password)
        await page.click('button[type="submit"]')

        # Optional: handle 2FA manually in the launched browser if needed
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        results = {}
        for kw in keywords:
            emails = await fetch_emails_for_keyword(page, kw, pages=pages)
            results[kw] = emails
        await browser.close()
        return results
