import asyncio
import json
import os
import time
import sys

from main import run_once_async

interval = int(sys.argv[1])

run_data = None
payload_path = None
if len(sys.argv) > 2:
    payload_path = sys.argv[2]
else:
    payload_path = os.getenv("RUN_PAYLOAD_PATH")

if payload_path and os.path.exists(payload_path):
    with open(payload_path, "r", encoding="utf-8") as f:
        run_data = json.load(f)


async def loop():
    while True:
        print("?? Loop Worker: Running pipeline...")
        await run_once_async(run_data)
        print(f"Sleeping {interval} minutes...")
        time.sleep(interval * 60)


asyncio.run(loop())
