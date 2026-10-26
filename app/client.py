#!/usr/bin/env python3
"""Fetch one content file through the CDN virtual IP."""

import argparse
import csv
import hashlib
import os
import socket
import sys
import time


CHUNK_SIZE = 64 * 1024
MAX_RETRIES = 5


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--host", default="10.0.0.100")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--client", default="c?")
    parser.add_argument("--log", default="results/data/client-transfers.csv")
    parser.add_argument("--tag", default="")
    parser.add_argument("--verify-dir", default="content")
    return parser.parse_args()


def recv_line(sock):
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("server closed before sending a response header")
        data.extend(chunk)
    return data.decode().strip()


def download(args):
    offset = 0
    total = 0
    retries = 0
    first_byte = None
    digest = hashlib.sha256()
    started = time.monotonic()

    while retries <= MAX_RETRIES:
        try:
            with socket.create_connection((args.host, args.port), timeout=3) as sock:
                sock.settimeout(2)
                sock.sendall(f"GET {args.name} {offset}\n".encode())
                header = recv_line(sock)
                if header.startswith("ERR"):
                    raise FileNotFoundError(header)

                _, total_text, remaining_text = header.split()
                total, remaining = int(total_text), int(remaining_text)
                received = 0
                while received < remaining:
                    chunk = sock.recv(min(CHUNK_SIZE, remaining - received))
                    if not chunk:
                        raise ConnectionError("server closed during content transfer")
                    if first_byte is None:
                        first_byte = time.monotonic()
                    digest.update(chunk)
                    received += len(chunk)
                    offset += len(chunk)
            break
        except FileNotFoundError as error:
            print(error)
            return 1
        except OSError:
            retries += 1
            if retries > MAX_RETRIES:
                print("FAILED")
                return 2
            time.sleep(min(2 ** (retries - 1), 4))

    elapsed = time.monotonic() - started
    ttfb = first_byte - started if first_byte is not None else 0
    log_path = args.log
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a", newline="") as log:
        csv.writer(log).writerow((args.tag, args.client, args.name, total,
                                  round(ttfb, 3), round(elapsed, 3),
                                  round(total * 8 / elapsed / 1e6, 2), retries))

    expected = hashlib.sha256()
    try:
        path = os.path.join(args.verify_dir, os.path.basename(args.name))
        with open(path, "rb") as content:
            for chunk in iter(lambda: content.read(1024 * 1024), b""):
                expected.update(chunk)
        checksum = "OK" if expected.digest() == digest.digest() else "MISMATCH"
    except OSError:
        checksum = "UNVERIFIED"

    print(f"{args.client} got {total} bytes in {elapsed:.2f}s, retries={retries} "
          f"checksum={checksum}")
    return 3 if checksum == "MISMATCH" else 0


if __name__ == "__main__":
    sys.exit(download(parse_args()))
