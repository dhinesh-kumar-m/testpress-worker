import os
import time
from datetime import datetime

while True:
    print(f"{datetime.now()} heartbeat pid={os.getpid()}", flush=True)
    time.sleep(5)
