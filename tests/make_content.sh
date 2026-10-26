#!/bin/bash
# creates the test files the servers deliver (not stored in git)
cd "$(dirname "$0")/.."
mkdir -p content
head -c 20M  /dev/urandom > content/video1.bin
head -c 100M /dev/urandom > content/video2.bin
head -c 5M   /dev/urandom > content/exp.bin
head -c 2M   /dev/urandom > content/small.bin
ls -lh content
