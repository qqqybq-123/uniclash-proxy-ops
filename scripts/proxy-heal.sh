#!/usr/bin/env bash
# 代理巡检：不通则自动切换节点，正常时静默无输出
exec /usr/bin/python3 /home/ubuntu/.hermes/scripts/proxyctl.py monitor
