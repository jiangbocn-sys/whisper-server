# whisper-server

OpenAI-compatible `/v1/audio/transcriptions` on Apple Silicon，跑在 Mac mini 上供 LAN 内 Windows 主机调用。后端是 [pywhispercpp](https://github.com/absadiki/pywhispercpp)（whisper.cpp 的 Python 绑定），**直接复用本机已下载的 `~/.cache/whisper-cpp/ggml-large-v3.bin`，无需再下模型**。

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
    model="ggml-large-v3",
    file=open("sample.wav", "rb"),
    language="zh",
    response_format="text",
))
```

### 健康检查

```bash
curl http://JiangdeMac-mini.local:8170/health
# {"status":"ok","model":".../ggml-large-v3.bin","n_threads":0,"vad":true,"vad_model":".../ggml-silero-v5.1.2.bin","backend":"pywhispercpp"}
```

> Windows 端如果 mDNS 不通（Bonjour 没装/被阻），把 `JiangdeMac-mini.local` 换成 Mac mini 内网 IP：`ifconfig | grep "inet " | grep -v 127.0.0.1`

## 部署

依赖：Python 3.11+（实测 3.12）、ffmpeg（处理非 16kHz 音频）、whisper.cpp 模型文件（默认读 `~/.cache/whisper-cpp/ggml-large-v3.bin`）、silero VAD 模型（默认读 `~/.cache/whisper-cpp/ggml-silero-v5.1.2.bin`）。

### 音频采样率

whisper.cpp 只接受 16 kHz mono PCM WAV；服务端用 ffmpeg 探测上传文件，自动重采样到 16kHz 再交给引擎。客户端无需关心。

### 手动启动（开发/调试）

```bash
cd /Users/bobo/projects/whisper-server
bash start.sh         # 创建 venv → pip install → nohup 后台启动
tail -f logs/server.log
bash stop.sh          # 优雅停
```

首次运行会编译 pywhispercpp 的 C 扩展（几十秒）；不下载 ASR 模型（ggml-large-v3.bin 已存在）。

如需启用 VAD 且 `~/.cache/whisper-cpp/ggml-silero-v5.1.2.bin` 不存在：

```bash
curl -L -o ~/.cache/whisper-cpp/ggml-silero-v5.1.2.bin \
  https://hf-mirror.com/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin
```

或临时关 VAD：`WHISPER_VAD=0 bash start.sh`。

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
| `WHISPER_MODEL` | `/Users/bobo/.cache/whisper-cpp/ggml-large-v3.bin` | 指向 `ggml-*.bin` 绝对路径。已下载的还有 `ggml-medium.bin` / `ggml-small.bin` 可切换 |
| `WHISPER_N_THREADS` | `0` | 0 = auto（`min(4, os.cpu_count())`）；arm64 上 4-8 即可 |
| `WHISPER_VAD` | `1` | whisper.cpp 内置 Silero VAD；设 `0` 关闭 |
| `WHISPER_VAD_MODEL` | `/Users/bobo/.cache/whisper-cpp/ggml-silero-v5.1.2.bin` | silero VAD ggml 文件 |
| `WHISPER_HOST` | `0.0.0.0` | 监听地址 |
| `WHISPER_PORT` | `8170` | 监听端口 |

launchd 把上述环境变量固化在 plist 里；改 plist 后跑一次 `launchctl unload && launchctl load` 即可。手动 `start.sh` 启动时由 shell 注入。

### 切换其他模型

```bash
ls ~/.cache/whisper-cpp/    # 看本机有哪些 ggml-*.bin
# 例如换成 medium（更快，质量略降）
WHISPER_MODEL=/Users/bobo/.cache/whisper-cpp/ggml-medium.bin bash start.sh
```

## 不在范围内

- API key 鉴权（LAN 信任）
- TLS（HTTPS / 自签证书）
- `/v1/audio/translations`（如需补，pywhispercpp Model 构造函数传 `translate=True` 即可）
- 自动下载模型（本机复用现有 ggml 文件）

## 文件

```
server.py                 FastAPI + pywhispercpp
requirements.txt          fastapi uvicorn pywhispercpp python-multipart
start.sh / stop.sh        本地手动启停
launchd/                  launchd plist + install/uninstall
```