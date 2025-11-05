🤖 LinkedIn Auto Emailer — Multi-Role, Visa-Aware Resume Sender

A fully automated LinkedIn content scanner and emailer that:

Searches LinkedIn posts for hiring keywords (e.g., “.NET Developer”, “Java Hiring”, “SDET”)

Extracts recruiter emails directly from post content

Filters out non-sponsoring posts (e.g., “No H1B”, “US Citizens Only”)

Prioritizes H1B-friendly or sponsorship-available posts

Sends customized emails for each role with the correct resume

Enforces a 10-day cooldown to avoid duplicate outreach

Generates a daily email report with all recruiter contacts and company summaries

🚀 Features

✅ LinkedIn Content Scraper

Uses Playwright to log in and scroll LinkedIn posts dynamically.

Extracts recruiter emails via BeautifulSoup parsing.

✅ Visa-Aware Smart Filtering

Skips posts mentioning “No H1B”, “US Citizen Only”, etc.

Prioritizes posts mentioning “H1B OK”, “Sponsorship available”, etc.

✅ Multi-Role Configuration

Separate resume and message templates for:

.NET Developer

SDET / QA Engineer

Java Developer

✅ Automatic Gmail Integration

Sends role-specific emails with attachments via Gmail API OAuth.

No passwords stored — uses google_client_secret.json and token.json.

✅ 10-Day Cooldown System

Prevents re-sending to the same recruiter for 10 days.

Stores contacts in data/seen.jsonl.

✅ Daily Summary Email

Automatically emails you a summary:

Roles processed

Recruiter emails and companies

Preferred / Neutral / Skipped post counts

✅ Ethical Use and Safety

Runs politely (configurable delay, user login)

Follows responsible automation practices

For personal networking and job search use only

🧰 Tech Stack

Python 3.10+

Playwright – for browser automation

BeautifulSoup (bs4) – for HTML parsing

Gmail API – for secure mail sending

Rich – for colorful CLI logging

dotenv – for credentials management

⚙️ Configuration

Edit config.json to define your roles:

"roles": [
  {
    "name": ".NET Developer",
    "keywords": [".NET Developer", "C# Developer"],
    "resume_path": "assets/RITHWIK_RAJ_MALLAM.doc",
    "message_subject": "Application: .NET Developer",
    "message_body": "..."
  },
  {
    "name": "SDET / QA Engineer",
    "keywords": ["SDET", "QA Engineer"],
    "resume_path": "assets/Rithwik_R_M.docx",
    "message_subject": "Application: SDET / QA Engineer",
    "message_body": "..."
  }
]

🧠 How It Works

Logs into LinkedIn with your credentials.

Searches each keyword from your config.

Skips posts that reject sponsorship.

Prioritizes posts open to H1B or sponsorship.

Extracts recruiter emails and sends personalized resumes.

Logs every email with company domain and timestamp.

Sends you a daily report email of all activities.

🧩 Folder Structure
auto-emailer-linkedin/
│
├── assets/                 # All resumes (per role)
├── data/                   # Cache (seen emails)
├── logs/                   # Daily email logs
├── main.py                 # Core logic (loop + cooldown + report)
├── linkedin_scraper.py     # Visa-aware scraper
├── gmail_helper.py         # Gmail API integration
├── cache.py                # Deduplication logic
├── config.json             # Roles & settings
├── .env                    # Credentials
└── requirements.txt

🕒 Run Modes
Mode	Behavior
"once"	Runs once, then stops
"loop"	Runs continuously at interval defined in loop_interval_minutes
⚖️ Disclaimer

This tool is designed for personal networking automation and not mass spam.
Respect LinkedIn’s terms of use, don’t send bulk emails, and use low-frequency intervals.
Always test with your own account responsibly.

📧 Example Daily Report
📅 Daily Report for 2025-11-04

🔹 Role: .NET Developer — 3 emails sent
  • hr@fusiongts.com (Fusiongts) via '.NET Developer'
  • recruiter@abc.com (Abc) via 'C# Developer'

🔹 Role: SDET / QA Engineer — 2 emails sent
  • xyz@talentgroup.com (Talentgroup) via 'SDET Hiring'

Preferred: 3 | Neutral: 2 | Skipped: 4
Total Emails Sent Today: 5

linkedin automation, job email bot, gmail api, python playwright, h1b sponsorship, resume sender, recruiter email scraper, .NET developer, SDET automation, job search tool

