# job_auto_apply.py
# Best-effort LinkedIn "Easy Apply" automation using Playwright.
# Adds:
#   - Required skills check on job description
#   - Better Easy Apply button detection
#   - More explicit status codes

from typing import Optional, Dict, List

from playwright.async_api import Page, Error


ASYNC_WAIT = 800  # ms


async def easy_apply_on_job(
    page: Page,
    job_url: str,
    resume_path: Optional[str] = None,
    required_skills: Optional[List[str]] = None,
    applicant_info: Optional[Dict] = None
) -> str:
    """
    Attempt "Easy Apply" on a LinkedIn job page.

    Returns one of:
      - "applied"
      - "already_applied"
      - "not_easy_apply"
      - "skills_mismatch"
      - "fail"
    """
    try:
        await page.goto(job_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(ASYNC_WAIT)

        # -------------------------------
        # OPTIONAL: REQUIRED SKILLS CHECK
        # -------------------------------
        if required_skills:
            try:
                # Best-effort: read full page text
                text_blob = (await page.content()).lower()
                hits = [s for s in required_skills if s.lower() in text_blob]

                if not hits:
                    print(f"[yellow]⚠ Skills mismatch for {job_url} – skipping[/yellow]")
                    return "skills_mismatch"
            except Error:
                pass

        # -------------------------------
        # EASY APPLY BUTTON DETECTION
        # -------------------------------
        selectors = [
            'button[aria-label*="Easy Apply"]',
            'button:has-text("Easy Apply")',
            'button[data-control-name*="jobdetails_topcard_inapply"]',
        ]

        btn = None
        for sel in selectors:
            try:
                btn = await page.wait_for_selector(sel, timeout=2500)
                if btn:
                    break
            except Error:
                continue

        if not btn:
            # Try to detect already-applied state
            try:
                applied_badge = await page.query_selector('span:has-text("Applied")')
                if applied_badge:
                    return "already_applied"
            except Error:
                pass

            return "not_easy_apply"

        await btn.click()
        await page.wait_for_timeout(ASYNC_WAIT)

        # -------------------------------
        # Upload resume if input present
        # -------------------------------
        try:
            upload = await page.query_selector('input[type="file"]')
            if upload and resume_path:
                await upload.set_input_files(resume_path)
                await page.wait_for_timeout(ASYNC_WAIT)
        except Error:
            pass

        # Fill basic info if fields exist (optional)
        if applicant_info:
            for label, value in applicant_info.items():
                if not isinstance(value, str):
                    continue
                try:
                    el = await page.query_selector(f'input[placeholder*="{label}"]') \
                         or await page.query_selector(f'text="{label}" >> xpath=.. >> input')
                    if el:
                        await el.fill(value)
                        await page.wait_for_timeout(300)
                except Error:
                    continue

        # -------------------------------
        # Step through multi-page form
        # -------------------------------
        async def click_if_exists(texts):
            for t in texts:
                try:
                    el = await page.wait_for_selector(f'button:has-text("{t}")', timeout=1500)
                    if el:
                        await el.click()
                        await page.wait_for_timeout(ASYNC_WAIT)
                        return True
                except Error:
                    continue
            return False

        steps = 0
        progressed = True
        while progressed and steps < 6:
            progressed = await click_if_exists(["Next", "Continue", "Review"])
            steps += 1

        # Final submit
        submitted = await click_if_exists(["Submit application", "Submit"])
        if submitted:
            return "applied"

        return "fail"

    except Error:
        return "fail"
