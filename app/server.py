#!/usr/bin/env python3
"""Serve files over TCP and report availability and load to the controller."""

import argparse
import os
import socket
import sys
import threading
import time


CHUNK_SIZE = 64 * 1024
HEARTBEAT_INTERVAL = 1
active_connections = 0
active_lock = threading.Lock()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dir", default="content")
    parser.add_argument("--ctrl", default="10.0.0.254")
    parser.add_argument("--ctrl-port", type=int, default=9000)
    return parser.parse_args()


def recv_line(conn):
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = conn.recv(1)
        if not chunk or len(data) >= 1024:
            raise ConnectionError("invalid request")
        data.extend(chunk)
    return data.decode().strip()


def handle(conn, args):
    global active_connections
    with active_lock:
        active_connections += 1
    try:
        conn.settimeout(10)
        parts = recv_line(conn).split()
        if len(parts) == 1 and parts[0] == "PING":
            with active_lock:
                count = active_connections
            conn.sendall(f"PONG {args.id} {count}\n".encode())
            return
        if len(parts) != 3 or parts[0] != "GET":
            conn.sendall(b"ERR BAD REQUEST\n")
            return

        path = os.path.join(args.dir, os.path.basename(parts[1]))
        offset = int(parts[2])
        if offset < 0 or not os.path.isfile(path):
            conn.sendall(b"ERR NOTFOUND\n")
            return

        size = os.path.getsize(path)
        conn.sendall(f"OK {size} {max(size - offset, 0)}\n".encode())
        with open(path, "rb") as content:
            content.seek(offset)
            while chunk := content.read(CHUNK_SIZE):
                conn.sendall(chunk)
    except (OSError, ValueError):
        pass
    finally:
        with active_lock:
            active_connections -= 1
        conn.close()


def send_heartbeat(args):
    last_error = None
    while True:
        with active_lock:
            count = active_connections
        try:
            with socket.create_connection((args.ctrl, args.ctrl_port), timeout=1) as conn:
                conn.sendall(f"STATUS {args.id} {count} {time.time()}\n".encode())
            if last_error:
                print(f"heartbeat to {args.ctrl}:{args.ctrl_port} restored", file=sys.stderr)
                last_error = None
        except OSError as error:
            message = str(error)
            if message != last_error:
                print(f"heartbeat to {args.ctrl}:{args.ctrl_port} failed: {message}",
                      file=sys.stderr)
                last_error = message
        time.sleep(HEARTBEAT_INTERVAL)


def main():
    args = parse_args()
    threading.Thread(target=send_heartbeat, args=(args,), daemon=True).start()
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", args.port))
        server.listen(64)
        print(f"server {args.id} listening on port {args.port}", flush=True)
        while True:
            conn, _ = server.accept()
            threading.Thread(target=handle, args=(conn, args), daemon=True).start()


if __name__ == "__main__":
    main()
