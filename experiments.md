# Experiments

All of these were run on my own machine (Ubuntu on WSL2, systemd 245). The screenshots are in `evidence/`.

Each one follows the same four parts: what I ran, what I expected, what actually happened, and why.

---

## 1. Finding the running program

Screenshots: `01-running-process-heartbeat.png`, `01-running-process-pgrep.png`

**Action:** Started `python3 app.py` in one terminal. In a second terminal I ran:

```
pgrep -af app.py
ps -o pid,ppid,stat,cmd -p $(pgrep -f app.py)
```

**Expectation:** The PID (the ID number Linux gives every running program) shown by `pgrep` would match the `pid=` in the heartbeat lines.

**Observation:** Both showed PID 748877. `ps` showed the state as `S+`, and the parent PID (PPID) was 745821.

**Explanation:** `S` means sleeping. The program spends almost all its time waiting inside `sleep(5)`, so that is the state you usually catch it in. The `+` means it is running in the front of the terminal, which is why Ctrl+C reaches it. The parent is the terminal (bash) that started it. Every program in Linux has a parent, and `pstree -ps <pid>` shows the whole family line back to systemd (PID 1).

---

## 2. Stopping with SIGTERM

Screenshots: `02-sigterm-app.png`, `02-sigterm-kill.png`

**Action:** Started `python3 app.py`, then in another terminal ran:

```
kill -TERM $(pgrep -f app.py)
```

**Expectation:** The program would print a shutdown message and exit by itself.

**Observation:** At 11:04:24 it printed `received SIGTERM, shutting down`. At 11:04:28 it printed `stopped cleanly` and exited.

**Explanation:** SIGTERM is a polite request to stop. Linux delivers it to the program, and the program decides what to do with it. My program catches it, sets a flag that ends the loop, and exits with code 0 (which means "all good"). The 4 second gap is because the program was in the middle of `sleep(5)`. It finished that wait, noticed the flag, and left the loop. That is the behaviour you want from a real worker: finish the current piece of work, then stop.

---

## 3. Stopping with SIGKILL

Screenshots: `03-sigkill-app.png`, `03-sigkill-kill.png`, `03-sigkill-commands.png`

**Action:** Started `python3 app.py` again, then ran:

```
kill -KILL $(pgrep -f app.py)
```

**Expectation:** The program would die immediately with no shutdown message.

**Observation:** The terminal just printed `Killed`. There was no `received ...` line and no `stopped cleanly`.

**Explanation:** SIGKILL never reaches the program. The Linux kernel removes it straight away, so none of its code gets to run, and it cannot be caught or ignored. Anything half done is lost. This is why you send SIGTERM first and only use SIGKILL if the program refuses to stop.

---

## 4. Running under systemd

Screenshot: `04-systemd-running.png`

**Action:** Created the `testpress` user, copied `app.py` to `/opt/testpress-worker/`, wrote `/etc/testpress-worker.env`, installed the service file, and ran:

```
sudo systemctl enable --now testpress-worker
systemctl status testpress-worker
ps -o user,pid,cmd -p $(pgrep -f app.py)
```

**Expectation:** The service would show as running and enabled, and the program would run as `testpress`, not root.

**Observation:** Status showed `active (running)` and `enabled`, PID 762136, and heartbeat lines at the bottom. `ps` showed the user as `testpre+` (`ps` cuts long names short and adds `+`; it is `testpress`).

**Explanation:** systemd started the program as the user named in `User=`. `enabled` means it will also start on boot. The heartbeat lines show up in `systemctl status` because the service sends its output to journald, systemd's log store.

My first try showed two warnings: `Assignment outside of section. Ignoring.` I had left out the `[Unit]` line at the top of the file, so systemd ignored the `Description` and `After` settings. The service still ran because the important settings were under `[Service]`. Adding `[Unit]` fixed it.

---

## 5. Automatic restart after a sudden kill

Screenshot: `05-auto-restart.png`

**Action:**

```
systemctl show -p MainPID testpress-worker
sudo kill -KILL $(systemctl show -p MainPID --value testpress-worker)
systemctl show -p MainPID testpress-worker
journalctl -u testpress-worker -n 15 --no-pager
```

**Expectation:** systemd would notice the program died and start a new one about 3 seconds later, with a new PID.

**Observation:** The PID changed from 762136 to 763285. The log showed:

- 11:22:42 `Main process exited, code=killed, status=9/KILL`
- 11:22:42 `Failed with result 'signal'`
- 11:22:45 `Scheduled restart job, restart counter is at 1`
- 11:22:45 the new program printed `started`

**Explanation:** The program was killed by a signal instead of exiting by itself, so systemd counts it as a failure. The service has `Restart=on-failure`, so it restarts it, and `RestartSec=3` is the 3 second wait. It is a brand new program, which is why the PID is different.

---

## 6. Stopping the service with SIGTERM

Screenshot: `extra-service-sigterm.png`

**Action:**

```
sudo kill -TERM $(systemctl show -p MainPID --value testpress-worker)
systemctl status testpress-worker --no-pager
```

**Expectation:** I wasn't sure. It is a kill, so maybe systemd would restart it like in experiment 5.

**Observation:** It was **not** restarted. Status showed `inactive (dead)` and `status=0/SUCCESS`. The log showed `received SIGTERM`, `stopped cleanly`, then `Succeeded`.

**Explanation:** My program catches SIGTERM and exits with code 0. To systemd, code 0 means "finished normally", and `Restart=on-failure` only restarts after a failure. Compared with experiment 5, the difference is not who sent the signal, but how the program ended.

---

## 7. Crashing with an error code

Screenshot: `06-crash-investigation.png`

**Action:** Set `CRASH_AFTER=3` in `/etc/testpress-worker.env`, then:

```
sudo systemctl restart testpress-worker
journalctl -u testpress-worker -n 30 --no-pager
```

**Expectation:** The program would crash after 3 heartbeats, and systemd would restart it each time.

**Observation:** Each run printed 3 heartbeats, then `simulated crash`. systemd logged `status=1/FAILURE` and `Failed with result 'exit-code'`, then restarted it 3 seconds later. The restart counter went 1, 2, 3, and each run had a new PID.

**Explanation:** Exit code 1 means "something went wrong", so systemd treats it as a failure and restarts it.

The problem is that this would go on forever. systemd's default limit is "give up after 5 starts within 10 seconds". Each run here lasted about 13 seconds, so the limit was never reached. `journalctl -p warning` showed it failing every 13 seconds from 11:27 to 11:29 until I stopped it. A service stuck like this looks fine from far away, but it is broken. That is why I added a proper limit in experiment 9.

---

## 8. Wrong program path

Screenshot: `07-invalid-config.png`

**Action:** In the installed service file, changed the start command to a program that does not exist:

```
ExecStart=/usr/bin/python3-wrong /opt/testpress-worker/app.py
```

Then ran `daemon-reload`, `restart`, `status` and `journalctl`.

**Expectation:** The service would fail to start.

**Observation:** The log showed `Failed at step EXEC spawning /usr/bin/python3-wrong: No such file or directory` and `status=203/EXEC`. Status showed `activating (auto-restart)`, because systemd kept trying.

**Explanation:** Code 203 is systemd's own code for "I could not even start the program". My Python code never ran, so there are no heartbeat lines at all. This is different from experiment 7, where the program ran and then crashed. Here it never started.

It also retried every 3 seconds, about 50 times, between 11:30:52 and 11:33:41, without ever giving up. The retries were about 3.3 seconds apart, slightly too slow to hit the default limit of 5 within 10 seconds.

I fixed it by copying the correct file from my project folder back into `/etc/systemd/system/`.

---

## 9. Repeated crashes and the restart limit

Screenshot: `08-rate-limit-journal.png`

**Action:** Added these two lines to the `[Unit]` section of the service file:

```
StartLimitIntervalSec=60
StartLimitBurst=5
```

Then set `CRASH_AFTER=1`, so the program crashes right after it starts, and ran:

```
sudo systemctl restart testpress-worker
journalctl -u testpress-worker -n 25 --no-pager
```

**Expectation:** After 5 starts within 60 seconds, systemd would stop trying.

**Observation:** The restart counter went up to 5. At 11:35:01 systemd logged `Start request repeated too quickly` and `Failed to start Testpress heartbeat worker`, and made no more attempts.

**Explanation:** The new lines mean "if this service starts 5 times within 60 seconds, give up". The service then stays failed until a person looks at it. A plain `restart` is not enough to bring it back. You first have to run `sudo systemctl reset-failed testpress-worker` to clear the failure. This is how a real crash loop gets noticed instead of hidden.

---

## 10. Memory limit

Screenshots: `09-resource-limits-config.png`, `09-resource-limits-oom.png`

**Action:** Added a setting to `app.py` that makes it grab more memory on every heartbeat. Added these lines to the `[Service]` section:

```
MemoryMax=50M
MemorySwapMax=0
CPUQuota=20%
```

Checked that they were active:

```
systemctl show testpress-worker -p MemoryMax -p MemorySwapMax -p CPUQuotaPerSecUSec
```

Then set `ALLOCATE_MB=10`, restarted, and read the log.

**Expectation:** Memory would climb 10 MB at a time until it passed 50 MB, and then the program would be killed.

**Observation:** `systemctl show` printed `MemoryMax=52428800` (50 MB in bytes), `MemorySwapMax=0` and `CPUQuotaPerSecUSec=200ms` (20% of one CPU). The log showed `holding 10 MB` up to `holding 40 MB`. On the next heartbeat systemd logged `A process of this unit has been killed by the OOM killer`, `status=9/KILL`, and `Failed with result 'oom-kill'`. It was then restarted, and the same thing happened again.

**Explanation:** systemd puts each service in a cgroup, a group that the Linux kernel can apply limits to. When the program asked for memory past 50 MB (40 MB of its own plus what Python itself uses), the kernel's OOM killer ("out of memory" killer) stopped it with SIGKILL. That is why the program logged nothing about it: SIGKILL cannot be caught. It counts as a failure, so systemd restarted it.

`MemorySwapMax=0` was needed because my machine has 8 GB of swap (disk space used as extra memory). Without it, the program would have spilled into swap instead of being killed.

The first time I set this up, `systemctl show` printed `infinity` for all three. I had not saved the file in nano, so the lines were never there. Checking with `systemctl show` caught it.

---

## 11. Starting after a reboot

Screenshot: `10-reboot-persistence.png`

**Action:** From Windows PowerShell ran `wsl --shutdown`, which stops the whole Linux system. Opened a new terminal, did not start anything myself, and ran:

```
uptime -s
systemctl status testpress-worker --no-pager
```

**Expectation:** The service would already be running.

**Observation:** The system booted at 11:47:19. The service was `active (running)` since 11:47:26 with PID 501. The journal shows `-- Reboot --` between the last stop and this start.

**Explanation:** `systemctl enable` linked the service to `multi-user.target`, the normal boot stage, through the `WantedBy=` line. So systemd starts it on every boot. The low PID (501) also shows it started very early. Before the shutdown, the log shows `received SIGTERM` and `stopped cleanly`, so systemd stopped it properly on the way down too.

---

## 12. Investigating a service that keeps crashing

These are the commands I would use, in this order:

1. `systemctl status testpress-worker` shows whether it is running, failed, or restarting, plus the last exit code (`status=1/FAILURE`, `203/EXEC`, `9/KILL`).
2. `systemctl show testpress-worker -p Result -p NRestarts -p ExecMainStatus` shows the reason for the last stop and how many times it has been restarted.
3. `journalctl -u testpress-worker -p warning` shows only warnings and errors, which is the fastest way to find the problem in a long log.
4. `journalctl -u testpress-worker -n 50` shows what the program printed just before it died.
5. `systemd-analyze verify /etc/systemd/system/testpress-worker.service` checks the file for mistakes.

The `Result` tells you which kind of problem it is:

- `exit-code` means the program ran and exited with an error, so the bug is in the program or its settings. Read its own log lines.
- `signal` means something killed it from outside.
- `oom-kill` means it used too much memory.
- `203/EXEC` means it never started, so check the path in `ExecStart`.

On my machine, `-p warning` showed the whole day's trouble in one list. After the reboot, `NRestarts` was back to 0.

---

## Questions for the demonstration

**What is the difference between SIGTERM and SIGKILL?**
SIGTERM asks the program to stop, and the program can clean up first or even ignore it. SIGKILL is done by the kernel, and the program cannot catch it or run any code.

**Why doesn't `nohup` provide the same reliability as systemd?**
`nohup` only stops the program from dying when you close the terminal. If the program crashes, nothing restarts it. If the server reboots, nothing starts it again. Its logs go to a file that nobody watches, and there are no memory limits.

**What happens when a service crashes repeatedly?**
systemd restarts it after each crash, as long as `Restart=` says so. If it starts too many times within a short time (`StartLimitBurst` within `StartLimitIntervalSec`), systemd gives up and marks it as failed until someone runs `reset-failed`.

**What is the difference between restarting a process and restarting a service?**
Restarting a process means you kill a program and start it again yourself. systemd doesn't know why, and doesn't keep the settings, user, limits or logs for you. Restarting a service means systemd stops it (SIGTERM first, then SIGKILL if it takes too long), then starts it again with the same user, settings and limits, and writes it all to the log.

**What happens to child processes when a systemd service is stopped?**
By default systemd stops every process in the service's cgroup, not just the main one. Children started by the program are stopped too, so nothing is left behind. This is controlled by `KillMode=`.

**How would you ensure a Celery worker finishes its current task before shutting down?**
Celery treats SIGTERM as "warm shutdown": it stops taking new tasks and finishes the ones it is running. My `app.py` does the same thing on a small scale. In the service file, I would set `TimeoutStopSec=` longer than the longest task, so systemd doesn't send SIGKILL before the task is done. `KillMode=mixed` sends SIGTERM only to the main Celery process and lets it shut down its own workers.
