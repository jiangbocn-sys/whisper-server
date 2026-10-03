# whisper-server

OpenAI-compatible `/v1/audio/transcriptions` on Apple Silicon，跑在 Mac mini 上供 LAN 内 Windows 主机调用。后端是 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（CTranslate2 + Silero VAD）。

## 使用

默认监听 `0.0.0.0:8170`，任何 LAN 主机可直接调。

### curl

```bash
curl -X POST http://JiangdeMac-mini.local:8170/v1/audio/transcriptions \
  -F "file=@sample.wav" \
  -F "language=zh" \
  -F "response_format=text"
```

可用 `response_format`：`json`（默认）/ `text` / `srt` / `vtt`。

### Python（openai sdk）

```python
from openai import OpenAI

c = OpenAI(base_url="http://JiangdeMac-mini.local:8170/v1", api_key="not-needed")
print(c.audio.transcriptions.create(
    model="Systran/faster-distil-whisper-large-v3",
    file=open("sample.wav", "rb"),
    language="zh",
    response_format="text",
))
```

### 健康检查

```bash
curl http://JiangdeMac-mini.local:8170/health
# {"status":"ok","model":"Systran/faster-distil-whisper-large-v3","compute_type":"float32","vad":true}
```

> Windows 端如果 mDNS 不通（Bonjour 没装/被阻），把 `JiangdeMac-mini.local` 换成 Mac mini 内网 IP：
> `ifconfig | grep "inet " | grep -v 127.0.0.1`

## 部署

依赖：Python 3.11+（实测 3.12）、ffmpeg（macOS 上 `brew install ffmpeg`）、可访问 huggingface.co 下载模型。

### 手动启动（开发/调试）

```bash
cd /Users/bobo/projects/whisper-server
bash start.sh         # 创建 venv → pip install → nohup 后台启动
tail -f logs/server.log
bash stop.sh          # 优雅停
```

首次运行会从 HuggingFace 下载 ~1.5 GB 模型到 `~/.cache/huggingface/`。

### launchd 守护（24h 主机）

```bash
cd /Users/bobo/projects/whisper-server/launchd
bash install.sh       # 装到 ~/Library/LaunchAgents，开机自起 + 崩溃自动重启
launchctl list | grep whisper-server   # 验证
tail -f ../logs/launchd.out.log

bash uninstall.sh     # 卸载
```

`Aqua` session：GUI 登录后拉起；纯 SSH session 不拉（避免无 GUI 时也抢端口）。

## 调优

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `WHISPER_MODEL` | `Systran/faster-distil-whisper-large-v3` | HuggingFace repo；可换 `Systran/faster-whisper-large-v3`（最准但慢）/ `Systran/faster-whisper-small`（最快） |
| `WHISPER_COMPUTE_TYPE` | `float32` | Apple Silicon 上推荐 `int8` 加速（质量损失可忽略），`float16` 不支持 |
| `WHISPER_VAD` | `1` | Silero VAD 静音过滤；设 `0` 关闭 |
| `WHISPER_BEAM_SIZE` | `5` | 越高越准越慢 |
| `WHISPER_HOST` | `0.0.0.0` | 监听地址 |
| `WHISPER_PORT` | `8170` | 监听端口 |

launchd 把上述环境变量固化在 plist 里；改 plist 后跑一次 `launchctl unload && launchctl load` 即可。手动 `start.sh` 启动时由 shell 注入。

## 不在范围内

- API key 鉴权（LAN 信任）
- TLS（HTTPS / 自签证书）
- `/v1/audio/translations`（如需补，三行代码）
- Docker（物理机直接跑）

## 文件

```
server.py                 FastAPI + faster-whisper
requirements.txt          fastapi uvicorn faster-whisper python-multipart
start.sh / stop.sh        本地手动启停
launchd/                  launchd plist + install/uninstall
```