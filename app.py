import os
import signal
import sys
import time
from datetime import datetime

running = True

INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "5"))
CRASH_AFTER = int(os.environ.get("CRASH_AFTER", "0"))

ALLOCATE_MB = int(os.environ.get("ALLOCATE_MB", "0"))
hog = []

def log(message):
    print(f"{datetime.now()} pid={os.getpid()} {message}", flush=True)


def handle_stop(signum, frame):
    global running
    log(f"received {signal.Signals(signum).name}, shutting down")
    running = False


signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)

log(f"started interval={INTERVAL} crash_after={CRASH_AFTER}")
count = 0
while running:
    count += 1
    log(f"heartbeat {count}")
    if ALLOCATE_MB:
        hog.append(bytearray(ALLOCATE_MB * 1024 * 1024))
        log(f"holding {len(hog) * ALLOCATE_MB} MB")
    if CRASH_AFTER and count >= CRASH_AFTER:
        log("simulated crash")
        sys.exit(1)
    time.sleep(INTERVAL)

log("stopped cleanly")
sys.exit(0)
