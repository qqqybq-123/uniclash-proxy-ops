#!/usr/bin/env python3
"""UniClash 代理管理/监测 CLI（.11 上的 9090 API，经 9092 映射到 LAN）

用法:
  proxyctl.py status            健康、出口、当前节点、模式
  proxyctl.py nodes             列出组与当前选择
  proxyctl.py test [组名]       批量测延迟（默认 Proxy）
  proxyctl.py use <节点名>      切节点（写 Proxy 组）
  proxyctl.py auto              自动选延迟最低的存活节点
  proxyctl.py mode rule|global  切模式
  proxyctl.py monitor           体检+自愈（供 cron 用，正常时静默）
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = os.environ.get('UNICLASH_API', 'http://127.0.0.1:9090')
PROXY = os.environ.get('UNICLASH_PROXY', 'http://127.0.0.1:7893')
GROUP = 'Proxy'
TEST_URL = 'http://www.gstatic.com/generate_204'

# 用户要求：不使用香港节点（延迟好看但实际体验差）
EXCLUDE_KW = ('香港', 'hk', 'hong')


def is_excluded(name):
    low = (name or '').lower()
    return any(k in low for k in EXCLUDE_KW)


def api(path, method='GET', body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def proxied(url, timeout=10):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
    t0 = time.time()
    try:
        with opener.open(url, timeout=timeout) as r:
            r.read(2048)
            return r.status, round(time.time() - t0, 2)
    except Exception as e:
        return type(e).__name__, round(time.time() - t0, 2)


def exit_ip():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
    try:
        with opener.open('https://api.ipify.org', timeout=10) as r:
            return r.read().decode().strip()
    except Exception:
        return '-'


def group_info(name=GROUP):
    d = api('/proxies/' + urllib.parse.quote(name, safe=''))
    return d.get('now'), d.get('all') or []


CHECK_URL = 'http://www.gstatic.com/generate_204'


def check(attempts=2, timeout=8):
    """健康判定：gstatic 204，失败重试一次（切节点后首包常超时）"""
    last = None
    for _ in range(attempts):
        code, secs = proxied(CHECK_URL, timeout=timeout)
        last = (code, secs)
        if isinstance(code, int) and code in (200, 204):
            return True, last
        time.sleep(1)
    return False, last


def cmd_status():
    node, _ = group_info()
    mode = api('/configs').get('mode')
    ok, (code, secs) = check()
    bcode, _ = proxied('http://www.baidu.com')
    print(f"代理: {'通' if ok else '不通'} (gstatic={code} {secs}s, baidu={bcode})")
    print(f"出口: {exit_ip()}")
    print(f"节点: {node}   模式: {mode}")
    if is_excluded(node):
        print('⚠ 当前是香港节点，按你的要求应切走：proxyctl.py auto')
    return 0 if ok else 1


def cmd_nodes():
    d = api('/proxies')['proxies']
    for k, v in d.items():
        if v.get('type') in ('Selector', 'URLTest', 'Fallback'):
            print(f"{k} [{v['type']}] now={v.get('now')} 可选={len(v.get('all') or [])}")


def cmd_test(name=GROUP):
    try:
        d = api(f'/group/{urllib.parse.quote(name, safe="")}/delay?timeout=5000&url=' +
                urllib.parse.quote(TEST_URL, safe=''), timeout=60)
    except Exception as e:
        print('批量测速不可用:', type(e).__name__)
        return 1
    alive = {k: v for k, v in d.items() if isinstance(v, int)}
    dead = [k for k, v in d.items() if not isinstance(v, int)]
    for k, v in sorted(alive.items(), key=lambda x: x[1])[:15]:
        print(f"{v:>5} ms  {k}")
    print(f"存活 {len(alive)} / 共 {len(alive) + len(dead)}")
    return 0


def cmd_use(node):
    if is_excluded(node) and '--force' not in sys.argv:
        print(f'拒绝切换到香港节点: {node}（用户要求不用香港节点；确需切用 --force）')
        return 1
    api('/proxies/' + urllib.parse.quote(GROUP, safe=''), 'PUT', {'name': node})
    now, _ = group_info()
    print('已切换到:', now)
    return 0


def cmd_auto():
    d = api(f'/group/{urllib.parse.quote(GROUP, safe="")}/delay?timeout=5000&url=' +
            urllib.parse.quote(TEST_URL, safe=''), timeout=60)
    alive = [(v, k) for k, v in d.items() if isinstance(v, int)]
    skipped = [k for v, k in alive if is_excluded(k)]
    alive = [(v, k) for v, k in alive if not is_excluded(k)]
    if skipped:
        print(f"跳过香港节点 {len(skipped)} 个: " + '、'.join(skipped[:4]) + ('…' if len(skipped) > 4 else ''))
    if not alive:
        print('没有可用（非香港）存活节点')
        return 1
    alive.sort()
    best = alive[0]
    api('/proxies/' + urllib.parse.quote(GROUP, safe=''), 'PUT', {'name': best[1]})
    print(f"已切到最快节点: {best[1]} ({best[0]}ms)")
    return 0


def cmd_mode(m):
    api('/configs', 'PATCH', {'mode': m})
    print('模式:', api('/configs').get('mode'))
    return 0


def cmd_monitor():
    ok, (code, _) = check(attempts=2, timeout=8)
    if ok:
        return 0
    before, _ = group_info()
    print(f"[{time.strftime('%m-%d %H:%M')}] 代理不通(gstatic={code})，当前节点 {before}，尝试自动切换")
    cmd_auto()
    time.sleep(2)
    ok2, (code2, _) = check(attempts=2, timeout=8)
    if ok2:
        now, _ = group_info()
        print(f"已自愈：{before} -> {now}，gstatic={code2}")
        return 0
    print(f"自愈失败：gstatic={code2}，需要人工介入（.11 上 UniClash 可能需重新点连接）")
    return 1


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    c = a[0]
    if c == 'status':
        return cmd_status()
    if c == 'nodes':
        return cmd_nodes()
    if c == 'test':
        return cmd_test(a[1] if len(a) > 1 else GROUP)
    if c == 'use':
        return cmd_use(a[1])
    if c == 'auto':
        return cmd_auto()
    if c == 'mode':
        return cmd_mode(a[1])
    if c == 'monitor':
        return cmd_monitor()
    print('未知命令', c)
    return 2


if __name__ == '__main__':
    sys.exit(main())
