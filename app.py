import os
import signal
import sys
import time
from datetime import datetime

running = True


def log(message):
    print(f"{datetime.now()} pid={os.getpid()} {message}", flush=True)

import signal
import sys
import time
from datetime import datetime

running = True


def log(message):
    print(f"{datetime.now()} pid={os.getpid()} {message}", flush=True)


def handle_stop(signum, frame):
    global running
    log(f"received {signal.Signals(signum).name}, shutting down")
    running = False


signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)

log("started")
while running:
    log("heartbeat")
    time.sleep(5)

log("stopped cleanly")
sys.exit(0)
