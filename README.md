🤖 LinkedIn Auto Emailer — Intelligent Multi-Role, Visa-Aware Resume Sender

A smart LinkedIn automation tool that scans public posts for hiring keywords, extracts recruiter emails, and automatically sends tailored resumes for each role.
It intelligently filters out posts that mention “No H1B” or “US Citizens Only,” prioritizes H1B-friendly listings, enforces a 10-day cooldown between contacts, and emails you a daily report with recruiter and company details.
Designed for personal, ethical use to streamline networking and job outreach.

🧩 Features

✅ LinkedIn Content Scanner

Uses Playwright to log in and scroll LinkedIn search results dynamically.

Extracts recruiter emails via BeautifulSoup parsing.

✅ Visa-Aware Filtering

Skips posts mentioning “No H1B”, “US Citizens Only”, or “No Sponsorship”.

Prioritizes posts mentioning “H1B OK”, “Sponsorship Available”, “Visa Supported”.

✅ Multi-Role Configuration

Supports multiple job roles (e.g., .NET Developer, SDET / QA Engineer, Java Developer).

Sends the appropriate resume and cover message for each role automatically.

✅ Smart Cooldown System

Avoids re-sending to the same recruiter within 10 days.

Maintains a local cache (data/seen.jsonl).

✅ Automated Gmail Integration

Sends personalized messages and resume attachments securely through Gmail API OAuth.

✅ Daily Email Report

Summarizes all emails sent, companies contacted, and skipped posts (H1B filters).

⚙️ Setup Guide
🧾 1️⃣ Prerequisites

Python 3.10+

Google Cloud Gmail API credentials (google_client_secret.json)

LinkedIn login credentials (email & password)

Playwright installed for Chromium browser automation

Install dependencies:

pip install -r requirements.txt
python -m playwright install chromium

🗂️ 2️⃣ Create Your assets/ Folder and Add Resumes

You must manually create an assets directory inside the project folder:

LinkedIn-Post-Emailer/
│
├── assets/
│   ├── Resume_NET.docx         # (for .NET Developer role)
│   ├── Resume_SDET.docx        # (for SDET / QA Engineer role)
│   ├── Resume_Java.docx        # (for Java Developer role)
│
├── main.py
├── config.json
└── ...


Then update the file names in your config.json to match your own resumes:

"roles": [
  {
    "name": ".NET Developer",
    "keywords": [".NET Developer", "C# Developer"],
    "resume_path": "assets/Resume_NET.docx",
    "message_subject": "Application: .NET Developer",
    "message_body": "Hello, I came across your post on LinkedIn for a .NET Developer position. Please find my resume attached."
  },
  {
    "name": "SDET / QA Engineer",
    "keywords": ["SDET Hiring", "QA Engineer"],
    "resume_path": "assets/Resume_SDET.docx",
    "message_subject": "Application: SDET / QA Engineer",
    "message_body": "Hello, I am interested in the SDET role you posted on LinkedIn. Please find my resume attached."
  },
  {
    "name": "Java Developer",
    "keywords": ["Java Hiring", "Spring Boot Developer"],
    "resume_path": "assets/Resume_Java.docx",
    "message_subject": "Application: Java Developer",
    "message_body": "Hello, I came across your post for a Java Developer role. Please find my resume attached."
  }
]

🔑 3️⃣ Set Up Gmail API

Go to Google Cloud Console → APIs & Services → Credentials

Create an OAuth Client ID → Desktop App

Download google_client_secret.json → place it in the project root

The first run will open a browser to authorize Gmail access

A token.json will be generated automatically (used for future runs)

⚠️ Never commit your google_client_secret.json or token.json to GitHub — keep them local and listed in .gitignore.

🧠 4️⃣ Configure Environment Variables

Create a .env file in your root folder:

LINKEDIN_EMAIL=your_linkedin_email
LINKEDIN_PASSWORD=your_linkedin_password
GMAIL_SENDER=your_gmail_address

🚀 5️⃣ Run the Script

Run once:

python main.py


Run in loop mode (every 15 minutes):

"run_mode": "loop",
"loop_interval_minutes": 15

📧 Example Daily Report
📅 Daily Report for 2025-11-04

🔹 Role: .NET Developer — 3 emails sent
  • hr@fusiongts.com (Fusiongts) via '.NET Developer'
  • recruiter@abc.com (Abc) via 'C# Developer'

🔹 Role: SDET / QA Engineer — 2 emails sent
  • xyz@talentgroup.com (Talentgroup) via 'SDET Hiring'

Preferred: 3 | Neutral: 2 | Skipped: 4  
Total Emails Sent Today: 5

🧾 Folder Structure
LinkedIn-Post-Emailer/
│
├── assets/                 # <-- Create manually and place your resumes here
├── data/                   # Cache (auto-generated)
├── logs/                   # Daily report logs
│
├── main.py                 # Main runner with cooldown + reporting
├── linkedin_scraper.py     # Visa-aware scraper
├── gmail_helper.py         # Gmail API mail sender
├── cache.py                # Duplicate prevention
├── config.json             # Role configuration
├── .env.example            # Sample environment file
├── .gitignore              # Protects credentials and temp files
└── requirements.txt        # Dependencies

⚖️ Disclaimer

This tool is for personal networking and job outreach automation only.
Use responsibly, respect LinkedIn’s Terms of Service, and avoid spam or excessive automation.
All credentials should be kept private and excluded from commits.
