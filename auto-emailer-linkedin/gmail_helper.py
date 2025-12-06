
from __future__ import annotations
import base64
import json
import os
from email.message import EmailMessage
from typing import List, Optional, Union

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def _load_credentials_from_token(token_data: Union[str, dict]) -> Credentials:
    """
    Build in-memory Credentials from a token.json payload supplied at runtime.
    """
    if isinstance(token_data, str):
        try:
            token_data = json.loads(token_data)
        except Exception as exc:
            raise ValueError(f"gmail_token is not valid JSON: {exc}") from exc

    if not isinstance(token_data, dict):
        raise ValueError("gmail_token must be a dict or JSON string")

    return Credentials.from_authorized_user_info(token_data, SCOPES)


def _get_gmail_service(token_data: Optional[Union[str, dict]] = None) -> any:
    """
    Build a Gmail service client.

    Priority:
      1. Explicit token payload passed in (per-user, not persisted)
      2. Local token.json refresh (legacy/local use)
      3. Trigger OAuth flow and persist token.json (legacy/local use)
    """
    if token_data:
        creds = _load_credentials_from_token(token_data)
        return build("gmail", "v1", credentials=creds)

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "google_client_secret.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def send_email_with_attachment(
    sender: str,
    to_addrs: List[str],
    subject: str,
    body_text: str,
    attachment_path: Optional[str] = None,
    token_data: Optional[Union[str, dict]] = None,
) -> dict:
    service = _get_gmail_service(token_data)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.set_content(body_text)

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            data = f.read()
        maintype = "application"
        subtype = "octet-stream"
        filename = os.path.basename(attachment_path)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    send_result = (
        service.users().messages().send(userId="me", body={"raw": encoded_message}).execute()
    )
    return send_result
