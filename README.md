# Testpress Worker

This is a small Python program that runs in the background and writes a "heartbeat" line every few seconds, so you can see it is still alive. It is managed by systemd, the part of Linux that starts programs at boot, restarts them when they crash, and keeps their logs.

The point of this project is not the program itself. It is a safe thing to break on purpose, so we can see how Linux and systemd react when a program crashes, gets killed, uses too much memory, or is set up wrong.

## What is in this folder

- `app.py` is the program.
- `testpress-worker.service` is the file that tells systemd how to run the program.
- `experiments.md` explains each experiment: what I ran, what I expected, what happened, and why.
- `evidence/` has screenshots of each experiment from my own machine.

## What you need

A Linux machine with systemd and Python 3. To check that systemd is running, run:

```
ps -p 1 -o comm=
```

It should print `systemd`. On WSL (Linux inside Windows), systemd is sometimes turned off. If you see something else, turn it on first.

## Settings

The program reads its settings from environment variables. These are named values you hand to a program when it starts.

| Setting | What it does | Default |
|---|---|---|
| `HEARTBEAT_INTERVAL` | Seconds between heartbeats | `5` |
| `CRASH_AFTER` | Crash on purpose after this many heartbeats. `0` means never. | `0` |
| `ALLOCATE_MB` | Grab this many MB of extra memory on every heartbeat, to test the memory limit. `0` means off. | `0` |

You can try it without systemd:

```
HEARTBEAT_INTERVAL=2 CRASH_AFTER=3 python3 app.py
```

Press Ctrl+C to stop it. The program catches the stop request, finishes what it is doing, and exits cleanly.

## Setting it up as a service

1. Create a user just for this program. It should not run as root, because root can do anything on the system, and a buggy program should not have that much power.

   ```
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin testpress
   ```

2. Copy the program to `/opt`, the usual place for apps you install yourself.

   ```
   sudo mkdir -p /opt/testpress-worker
   sudo cp app.py /opt/testpress-worker/
   ```

3. Create the settings file.

   ```
   sudo nano /etc/testpress-worker.env
   ```

   Put this inside:

   ```
   HEARTBEAT_INTERVAL=5
   CRASH_AFTER=0
   ALLOCATE_MB=0
   ```

4. Install the service file and start it.

   ```
   sudo cp testpress-worker.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now testpress-worker
   ```

   `daemon-reload` tells systemd to read the new file. `enable --now` starts the service now and also on every boot.

5. Check that it is running.

   ```
   systemctl status testpress-worker
   ```

   You should see `active (running)` and a few heartbeat lines.

## What the service file does

- Runs the program as the `testpress` user.
- Loads settings from `/etc/testpress-worker.env`.
- Restarts the program 3 seconds after it crashes, but only after a crash. If the program stops cleanly, it is left stopped.
- Gives up if the program has to be started 5 times within 60 seconds. Without this, a broken program would be restarted forever and nobody would notice.
- Sends everything the program prints to the system log, which you can read with `journalctl`.
- Limits the program to 50 MB of memory, no swap (disk space used as extra memory), and 20% of one CPU core.
- Starts the program on boot.

## Everyday commands

```
systemctl status testpress-worker          # is it running, and the last few log lines
sudo systemctl stop testpress-worker       # stop it
sudo systemctl start testpress-worker      # start it
sudo systemctl restart testpress-worker    # stop it, then start it
journalctl -u testpress-worker -f          # watch the log live (Ctrl+C to quit)
journalctl -u testpress-worker -p warning  # only warnings and errors
```

If you change the service file, copy it again and run `sudo systemctl daemon-reload`. If you change `app.py`, copy it to `/opt/testpress-worker/` again and restart the service.

If the service keeps crashing and systemd gives up, it stays stopped until you fix the problem and run:

```
sudo systemctl reset-failed testpress-worker
sudo systemctl start testpress-worker
```

## Repeating the experiments

Every experiment is written up step by step in `experiments.md`. Most of them only need a change to `/etc/testpress-worker.env` and a restart. Remember to set the values back to `0` afterwards.

## Removing everything

```
sudo systemctl disable --now testpress-worker
sudo rm /etc/systemd/system/testpress-worker.service /etc/testpress-worker.env
sudo rm -r /opt/testpress-worker
sudo systemctl daemon-reload
sudo userdel testpress
```
