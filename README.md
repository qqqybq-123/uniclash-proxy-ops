# uniclash-proxy-skill

一个 Hermes / Claude 风格的 skill：**UniClash（Clash 内核 + Flutter GUI）在 Windows 上"端口在听但不转发"的排查与脚本化控制**。

## 解决什么问题

- GUI 在跑、mixed-port 在 LISTENING，但所有连接被立即关闭（curl 返回 `000`）
- 明明节点能测出延迟，翻墙却完全不通
- 想从别的机器上脚本化切节点 / 测速 / 巡检自愈
- 巡检脚本每 5 分钟把节点切到香港，延迟好看但实际难用

## 结论摘要

| 现象 | 根因 | 修法 |
|---|---|---|
| 端口监听但不转发 | `shared_preferences.json` 里 `appSettingProps.autoRun = false` | 改 `true` 后重启 GUI |
| 远程点不到 GUI | GUI 落在 Session 0 | `AutoAdminLogon` + `/it` 计划任务 |
| 改不了节点列表 | profile 是 `UCENC:1` 私有加密 | 只能在 GUI/API 内选已有节点 |
| 巡检切香港 | 按延迟排序 | 排除 `香港/HK/Hong` 关键字 |

## 用法

```bash
export UNICLASH_API=http://<LAN_IP>:<API_PORT>     # 即内核 external-controller（默认 9090）
export UNICLASH_PROXY=http://<LAN_IP>:<MIXED_PORT> # 即 mixed-port

python3 scripts/proxyctl.py status    # 健康 + 出口 IP + 当前节点 + 模式
python3 scripts/proxyctl.py nodes     # 组与当前选择
python3 scripts/proxyctl.py test      # 批量测延迟
python3 scripts/proxyctl.py use <节点名>
python3 scripts/proxyctl.py auto      # 自动选最快（自动跳过香港）
python3 scripts/proxyctl.py mode rule|global
python3 scripts/proxyctl.py monitor   # 体检 + 自愈，正常时静默（cron 用）
```

把 `monitor` 挂到 cron 每 5 分钟一次即可：

```cron
*/5 * * * * UNICLASH_API=http://10.0.0.5:9092 UNICLASH_PROXY=http://10.0.0.5:7897 python3 /path/proxyctl.py monitor
```

## 作为 skill 安装

```bash
git clone <this repo> ~/.hermes/skills/uniclash-proxy-ops
```

Hermes 会在匹配到代理/网络排查类任务时加载 `SKILL.md`。

## 安全边界

- 控制面别直接绑 `0.0.0.0`；用 `netsh portproxy` 映射到内网端口并限制 `remoteip`
- 校验配置文件里可能带账号邮箱、订阅 token，提交前自行清理
- 本仓库不含任何真实地址、节点名、凭据

## License

MIT
