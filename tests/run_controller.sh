#!/bin/bash
# usage: tests/run_controller.sh [dynamic|static]
cd "$(dirname "$0")/.."
source ~/ryu-env/bin/activate
CDN_MODE=${1:-dynamic} exec ryu-manager controller/cdn_controller.py
