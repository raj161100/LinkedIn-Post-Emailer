import asyncio
from playwright.async_api import async_playwright

async def test_login():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.linkedin.com/login")
        await page.fill('input#username', "your_email_here")
        await page.fill('input#password', "your_password_here")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("domcontentloaded")

        print("Current URL:", page.url)
        await asyncio.sleep(5)
        await browser.close()

asyncio.run(test_login())
