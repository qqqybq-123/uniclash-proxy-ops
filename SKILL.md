---
name: uniclash-proxy-ops
description: Use when a UniClash (Clash-based) proxy on a Windows host "looks alive but passes no traffic", or when you need scripted node switching / health monitoring for it. Covers the autoRun=false false-alive bug, the external-controller control plane, LAN portproxy exposure, and a no-HK node policy.
---

# UniClash 代理运维（Windows 主机）

UniClash 是 Clash 内核 + Flutter GUI 的 Windows 客户端。它的坑在于：**GUI 看着在跑、端口也 LISTENING，但所有连接一进来就被关掉**，而内核 API 一切正常。本文记录定位与脚本化控制方法。

## 1. 假活症状与根因

症状：
- `127.0.0.1:<mixed-port>` 确实 LISTENING
- `curl -x http://host:port https://www.google.com` 返回码 `000`，连接被立即关闭
- PowerShell `Invoke-WebRequest -Proxy` 报「基础连接已经关闭: 接收时发生错误」
- 但 external-controller 的 `/proxies`、`/<group>/delay` 全部正常，节点也能测出延迟

根因：`%APPDATA%\UniClash\UniClash\shared_preferences.json` 里 `flutter.config.appSettingProps.autoRun = false`。此时 GUI 只挂了端口，内核不接管转发。改回 `true` 并重启 GUI 即可，**不需要重装、不需要换客户端**。

同一文件里还有：
- `appSettingProps.autoLaunch` 开机自启
- `appSettingProps.externalController` 是否开控制面
- `patchClashConfig.mixed-port` / `patchClashConfig.external-controller`
- `networkProps.systemProxy` 系统代理

`flutter.config` 是一段 JSON 字符串（转义后嵌在 prefs 里），改的时候整体改完再写回。

## 2. 控制面

打开 `externalController` 后，内核在 `127.0.0.1:9090` 起 mihomo REST API：

```bash
curl http://127.0.0.1:9090/version                  # {"meta":true,"version":"1.10.0"}
curl http://127.0.0.1:9090/proxies                  # 组与节点
curl http://127.0.0.1:9090/proxies/<组名>?           # 单组详情
curl "http://127.0.0.1:9090/group/<组名>/delay?timeout=5000&url=http://www.gstatic.com/generate_204"
curl -X PUT http://127.0.0.1:9090/proxies/<组名> -d '{"name":"<节点名>"}'
```

要跨机用时，别把 9090 直接绑 0.0.0.0，用 `netsh portproxy` 映射到一个局域网端口并只放行内网网段：

```powershell
netsh interface portproxy add v4tov4 listenaddress=<LAN_IP> listenport=<API_PORT> connectaddress=127.0.0.1 connectport=9090
netsh advfirewall firewall add rule name="uniclash-api" dir=in action=allow protocol=TCP localport=<API_PORT> remoteip=<LAN_CIDR>
```

## 3. GUI 在 Session 0 的问题

通过 WinRM / 计划任务拉起的 Flutter GUI 会落在 Session 0，界面不可见、点不到。可用替代：
- 写 `AutoAdminLogon`（`DefaultUserName`/`DefaultPassword`/`DefaultDomainName=.`）让机器自动登录到桌面会话
- 建 `/sc onlogon /ru <user> /rl HIGHEST /it` 的计划任务拉起 `uniclash.exe`

注意 `/it` 只对交互会话有效，配合自动登录才成立。

## 4. profile 是加密的

`profiles\*.yaml` 开头若为 `UCENC:1`，是应用私有加密，AESGCM / ChaCha20 / HKDF 各种组合都试过，解不开。后果：**只能在 GUI 或 API 里选已有节点，不能从外部改写节点列表或新增订阅**。订阅必须走应用自身的登录态。

## 5. 节点策略：不要用香港节点

香港节点延迟常最低（100–180ms），但实际吞吐/稳定性差（"看起来香，吃起来臭"）。脚本自动选节点时必须把 HK 排除，否则每 5 分钟一次的巡检会反复切到香港。

```python
EXCLUDE_KW = ('香港', 'hk', 'hong')
def is_excluded(name): return any(k in (name or '').lower() for k in EXCLUDE_KW)
```

## 6. 脚本

`scripts/proxyctl.py`：status / nodes / test / use / auto / mode / monitor。API 与代理地址从环境变量取：

```bash
export UNICLASH_API=http://<LAN_IP>:<API_PORT>
export UNICLASH_PROXY=http://<LAN_IP>:<MIXED_PORT>
python3 proxyctl.py status
```

`monitor` 子命令给 cron 用：正常时完全静默，不通才切节点并输出一行。

## 7. 验收

```bash
python3 proxyctl.py status      # 代理: 通 (gstatic=204 0.1s, baidu=200) / 出口 IP / 当前节点 / 模式
curl -x $UNICLASH_PROXY -s -o /dev/null -w '%{http_code}\n' https://www.google.com   # 期望 302
```

## 常见坑

- 判定健康要重试：切节点后首包常超时，单次判定会误报。`attempts=2`。
- API 请求要绕开 shell 环境代理，否则 `http_proxy` 会把你对 API 的请求也塞进代理形成自环（Python：`build_opener(ProxyHandler({}))`）。
- 别同时跑第二个 mihomo 实例占同一个 mixed-port，会互相抢端口。
- `PUT /proxies/<组>` 用 PowerShell 发送时会被默认编码加上 BOM，返回 400；用 UTF-8 无 BOM 的 body 或 `curl --data-binary`。
