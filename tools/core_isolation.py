#!/usr/bin/env python3
"""Optional Raspberry Pi boot isolation. Default action is a read-only plan.

CPU affinity already works without this script. Scheduler-domain isolation is
optional, requires a reboot, and is not a hard-real-time guarantee.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def digest(data):
    return hashlib.sha256(data).hexdigest()


def proposed(text, core=3, count=4):
    if count < 4 or core < 2 or core >= count:
        raise ValueError("Keep CPUs 0 and 1 available; select an existing CPU >=2 on a system with at least 4 CPUs")
    if len(text.strip().splitlines()) != 1 or not any(x.startswith("root=") for x in text.split()):
        raise ValueError("Expected a single-line Pi kernel command line containing root=")
    keys = ("isolcpus=", "irqaffinity=", "nohz_full=", "rcu_nocbs=")
    if any(x.startswith(keys) for x in text.split()):
        raise ValueError("Existing isolation/IRQ options found; review them manually rather than appending conflicts")
    others = ",".join(str(c) for c in range(count) if c != core)
    return text.strip()+f" isolcpus=domain,managed_irq,{core} irqaffinity={others}\n"


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix=".pulsebridge-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(name, path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", type=Path, help="Restore the exact backup JSON created by --apply")
    args = parser.parse_args()
    if args.apply and args.restore:
        parser.error("Choose apply or restore")
    model = Path("/proc/device-tree/model")
    if not model.exists() or b"Raspberry Pi" not in model.read_bytes():
        raise SystemExit("This tool only edits boot files on an actual Raspberry Pi")
    if args.restore:
        if os.geteuid() != 0:
            raise SystemExit("Restore requires sudo")
        backup = json.loads(args.restore.read_text())
        target = Path(backup["path"])
        if str(target) not in {"/boot/firmware/cmdline.txt", "/boot/cmdline.txt"}:
            raise SystemExit("Backup does not refer to a supported Pi boot file")
        if digest(target.read_bytes()) != backup["after_sha256"]:
            raise SystemExit("Boot options changed since apply; inspect and restore manually")
        original = backup["original"].encode()
        if digest(original) != backup["before_sha256"]:
            raise SystemExit("Backup integrity check failed")
        atomic_write(target, original)
        print("Restored", target, "Reboot manually when ready.")
        return
    path = next((p for p in (Path("/boot/firmware/cmdline.txt"), Path("/boot/cmdline.txt")) if p.is_file()), None)
    if path is None:
        raise SystemExit("Pi kernel command-line file not found")
    old = path.read_text()
    new = proposed(old, args.core, os.cpu_count() or 0)
    print("File:", path)
    print("Current:", old.strip())
    print("Proposed:", new.strip())
    print("This isolates scheduler placement and requests IRQ steering. It does not eliminate all IRQs or kernel jitter.")
    print("nohz_full is deliberately omitted: the UART receiver uses frequent system calls and multiple threads.")
    if not args.apply:
        print("Read-only plan. Apply only after a working baseline: sudo python3 tools/core_isolation.py --apply")
        return
    if os.geteuid() != 0:
        raise SystemExit("Apply requires sudo")
    backup = path.with_name("pulsebridge-cmdline-backup-"+str(time.time_ns())+".json")
    backup.write_text(json.dumps(dict(path=str(path), original=old, before_sha256=digest(old.encode()),
                                      after_sha256=digest(new.encode())), indent=2))
    atomic_write(path, new.encode())
    print("Applied. Exact backup:", backup)
    print("Reboot manually. Restore command: sudo python3 tools/core_isolation.py --restore", backup)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
