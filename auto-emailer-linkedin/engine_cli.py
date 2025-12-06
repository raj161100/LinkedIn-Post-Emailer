# IMPORTANT: Copy this file to the OLD auto-emailer-linkedin project as: engine_cli.py
# 
# Location: E:/Users/.../Downloads/auto-emailer-linkedin/auto-emailer-linkedin/engine_cli.py
#
# This file wraps your existing engine to be called from the SaaS platform.
# It does NOT change your existing run_once() behavior.

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

# Import your existing engine functions
try:
    from main import load_config, run_once
except ImportError:
    print("ERROR: Could not import from main.py")
    print("Make sure this file is in the same directory as main.py")
    raise

BASE_DIR = Path(__file__).resolve().parent


def copy_config(src: Path):
    """Copy provided config.json into the engine's root as config.json."""
    dest = BASE_DIR / "config.json"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[CLI] Using config from {src} -> {dest}")


def read_today_log() -> list:
    """
    Read today's sent_YYYY-MM-DD.jsonl and return compact results.
    De-duplicates by (email, role, keyword) tuple.
    """
    logs_dir = BASE_DIR / "logs"
    today = datetime.now().strftime("%Y-%m-%d")
    path = logs_dir / f"sent_{today}.jsonl"
    
    if not path.exists():
        print(f"[CLI] No log file found at {path}")
        return []

    results = []
    seen = set()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
            except Exception as e:
                print(f"[CLI] Skipping malformed line: {e}")
                continue

            email = data.get("email")
            if not email:
                continue
                
            key = (email, data.get("role"), data.get("keyword"))
            if key in seen:
                continue  # skip duplicates

            seen.add(key)
            results.append(
                {
                    "timestamp": data.get("timestamp"),
                    "email": email,
                    "role": data.get("role"),
                    "keyword": data.get("keyword"),
                    "company": data.get("company"),
                    "preferred": bool(data.get("preferred_bucket")),
                    "post_url": data.get("post_url"),
                }
            )
    
    print(f"[CLI] Read {len(results)} unique emails from {path}")
    return results



def main():
    parser = argparse.ArgumentParser(description="RajAI LinkedIn Engine CLI Bridge")
    parser.add_argument(
        "--config",
        required=True,
        type=str,
        help="Path to config.json for this run"
    )
    parser.add_argument(
        "--output",
        required=True,
        type=str,
        help="Path to write results.json output"
    )
    parser.add_argument(
        "--payload",
        required=False,
        type=str,
        help="Optional path to payload.json containing linkedin/gmail credentials"
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    output_path = Path(args.output)
    payload_data = None

    if args.payload:
        payload_path = Path(args.payload)
        if not payload_path.exists():
            raise SystemExit(f"ERROR: Payload file {payload_path} does not exist")
        payload_data = json.loads(payload_path.read_text(encoding="utf-8"))

    if not config_path.exists():
        raise SystemExit(f"ERROR: Config file {config_path} does not exist")

    try:
        # 1) Copy config into engine root as config.json
        copy_config(config_path)

        # 2) Run your existing pipeline ONCE with injected credentials
        print("[CLI] Starting engine run_once()...")
        run_once(payload_data)
        print("[CLI] Engine run_once() completed")

        # 3) Read today's logs & write results.json
        results = read_today_log()
        print(f"[CLI] Collected {len(results)} email records")

        output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"[CLI] Results written to {output_path}")

    except Exception as e:
        print(f"[CLI] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
