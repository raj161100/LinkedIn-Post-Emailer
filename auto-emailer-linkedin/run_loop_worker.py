# run_loop_worker.py

import asyncio
import time
import sys
from main import run_once_async

interval = int(sys.argv[1])

async def loop():
    while True:
        print("🔁 Loop Worker: Running pipeline...")
        await run_once_async()
        print(f"Sleeping {interval} minutes...")
        time.sleep(interval * 60)

asyncio.run(loop())
