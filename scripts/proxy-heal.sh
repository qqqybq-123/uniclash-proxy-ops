#!/usr/bin/env bash
# 代理巡检：不通则自动切换节点，正常时静默无输出
# 需要先 export UNICLASH_API / UNICLASH_PROXY
exec python3 "$(dirname "$0")/proxyctl.py" monitor
