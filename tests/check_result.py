#!/usr/bin/env python3
# usage: check_result.py <client output file> <minimum retries>
import re, sys
path, min_retries = sys.argv[1], int(sys.argv[2])
txt = open(path).read()
m = re.search(r'got (\d+) bytes in ([0-9.]+)s, retries=(\d+) checksum=OK', txt)
if not m:
    print('FAIL: no result line with checksum=OK in', path)
    sys.exit(1)
if int(m.group(3)) < min_retries:
    print('FAIL: expected at least', min_retries, 'retries, got', m.group(3))
    sys.exit(1)
print('PASS:', m.group(0))
