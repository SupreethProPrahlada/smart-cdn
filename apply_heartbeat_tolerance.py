#!/usr/bin/env python3
"""Give server heartbeat connections more tolerance under Mininet load."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
changes = {}


def replace_once(path, old, new):
    text = changes.get(path)
    if text is None:
        text = (ROOT / path).read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one matching section in {path}, found {count}. "
            "No files have been changed; use the current smart-cdn branch."
        )
    changes[path] = text.replace(old, new, 1)


replace_once(
    "app/server.py",
    "HEARTBEAT_INTERVAL = 1\n",
    "HEARTBEAT_INTERVAL = 1\n"
    "# Allow brief Mininet/OVS delays during concurrent downloads before a beat fails.\n"
    "HEARTBEAT_CONNECT_TIMEOUT = 3\n",
)

replace_once(
    "app/server.py",
    "            with socket.create_connection((args.ctrl, args.ctrl_port), timeout=1) as conn:\n",
    "            with socket.create_connection((args.ctrl, args.ctrl_port),\n"
    "                                          timeout=HEARTBEAT_CONNECT_TIMEOUT) as conn:\n",
)

replace_once(
    "README.md",
    "received byte; it allows 12 retries. The runner restarts the server afterward.\n",
    "received byte; it allows 12 retries. The runner restarts the server afterward.\n"
    "Servers send a heartbeat every second, allowing up to three seconds for each heartbeat connection attempt. "
    "A server is marked down only after ten seconds without a received heartbeat; a timeout followed by a "
    "restored message indicates that a later attempt succeeded.\n",
)

for relative, content in changes.items():
    file_path = ROOT / relative
    backup = file_path.with_suffix(file_path.suffix + ".before-heartbeat-timeout")
    if not backup.exists():
        shutil.copy2(file_path, backup)
    file_path.write_text(content, encoding="utf-8")

print("Heartbeat connection timeout is now 3 seconds; controller health timeout remains 10 seconds.")
print("Source backups are saved beside modified files with suffix .before-heartbeat-timeout.")
