#!/bin/bash
cd "$(dirname "$0")/.."
exec sudo python3 topology/topo.py
