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

## 供其他项目调用

> 写给需要把音频转写集成进自己应用的调用方。模型选型 / 部署 / 调优细节看上面"部署 / 调优"两节，本节只讲"当成一个 HTTP API 怎么用"。

### 端点

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/v1/audio/transcriptions` | POST | OpenAI 兼容的音频转写（multipart/form-data） |
| `/health` | GET | 健康检查 + 当前模型 / VAD 状态 |
| `/v1/models` | GET | OpenAI 兼容，返回当前加载的模型 id |

服务地址：默认 `http://JiangdeMac-mini.local:8170`（macOS mDNS），Windows / Linux 客户端若不通换成 Mac mini 内网 IP（`ifconfig | grep "inet "`）。

**不需要 API key**（LAN 信任），base_url 写服务地址即可，OpenAI SDK 的 `api_key` 字段随便填一个占位字符串。

### 当前实例配置

| 字段 | 值 |
| --- | --- |
| 模型 | `ggml-large-v3`（whisper large-v3，~3GB） |
| 设备 | Mac mini (Apple Silicon, M4) |
| 后端 | pywhispercpp + Metal GPU |
| VAD | silero v5.1.2（启用，会自动跳过静音段） |
| 监听 | `0.0.0.0:8170`，LAN 内任意主机可达 |
| 守护 | launchd，开机自起 + 崩溃 10s 重启 |

预期性能：3-5s 短音频 ~1.5s 处理完；1 分钟音频 ~10-15s。Metal GPU 单实例串行处理，并发请求会排队。

### 支持的请求参数

`/v1/audio/transcriptions` 接受 `multipart/form-data`，字段如下（OpenAI 兼容子集）：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | 音频文件，任意 ffmpeg 能解码的格式（wav/mp3/m4a/flac/ogg/webm…） |
| `model` | 是 | 写 `ggml-large-v3`（与 `/v1/models` 返回一致） |
| `language` | 否 | ISO-639-1，如 `zh` / `en` / `ja`；不传则自动检测 |
| `response_format` | 否 | `json`（默认）/ `text` / `srt` / `vtt` |
| `prompt` | 否 | 上一段文本提示，用于热词偏置；空字符串忽略 |

以下 OpenAI 参数**不支持**（传了会被忽略，**不会报错**）：`temperature`、`timestamp_granularities`（输出固定 `start`/`end` 二级时间戳）。

### 调用示例

#### curl（任何语言都能用）

```bash
# JSON（默认）
curl -X POST http://JiangdeMac-mini.local:8170/v1/audio/transcriptions \
  -F "file=@sample.wav" \
  -F "language=zh"

# 纯文本
curl -X POST http://JiangdeMac-mini.local:8170/v1/audio/transcriptions \
  -F "file=@sample.mp3" \
  -F "language=en" \
  -F "response_format=text"

# 字幕
curl -X POST http://JiangdeMac-mini.local:8170/v1/audio/transcriptions \
  -F "file=@voice.m4a" \
  -F "response_format=srt"
```

#### Python（openai sdk，最常用）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://JiangdeMac-mini.local:8170/v1",
    api_key="not-needed",   # LAN 信任，填什么都行
)

# response_format=json → 返回带 segments 的对象
result = client.audio.transcriptions.create(
    model="ggml-large-v3",
    file=open("sample.wav", "rb"),
    language="zh",
    response_format="json",
)
print(result.text)
for s in result.segments:
    print(f"[{s.start:.2f}-{s.end:.2f}] {s.text}")

# response_format=text → 返回纯字符串
text = client.audio.transcriptions.create(
    model="ggml-large-v3",
    file=open("sample.mp3", "rb"),
    language="en",
    response_format="text",
)
```

#### Node.js（openai sdk）

```js
import OpenAI from "openai";
import fs from "node:fs";

const client = new OpenAI({
  baseURL: "http://JiangdeMac-mini.local:8170/v1",
  apiKey: "not-needed",
});

const result = await client.audio.transcriptions.create({
  model: "ggml-large-v3",
  file: fs.createReadStream("sample.wav"),
  language: "zh",
  response_format: "text",
});
console.log(result);
```

#### 其他语言

任意能发 multipart POST 的 HTTP 客户端都行（Go `mime/multipart`、Rust `reqwest` + `multipart`、Java `HttpClient` + `MultipartEntityBuilder` 等）。**不需要** OpenAI SDK，直接对端点发请求即可。

### 响应格式

#### `response_format=json`（默认）

```json
{
  "language": "en",
  "text": "Hello, this is a test of the Whisper server with auto-resampling.",
  "segments": [
    {
      "id": 0,
      "start": 0.03,
      "end": 3.58,
      "text": "Hello, this is a test of the Whisper server with auto-resampling.",
      "no_speech_prob": null
    }
  ]
}
```

注意：`segments[].no_speech_prob` 永远是 `null`（whisper.cpp 不返回这个字段），客户端代码不要据此判断。

#### `response_format=text`

纯字符串，无 JSON 包装。

#### `response_format=srt`

```
1
00:00:00,030 --> 00:00:03,580
Hello, this is a test of the Whisper server with auto-resampling.
```

#### `response_format=vtt`

```
WEBVTT

00:00:00.030 --> 00:00:03.580
Hello, this is a test of the Whisper server with auto-resampling.
```

### 输入约束

- **格式**：任何 ffmpeg 能解码的容器 / 编码（服务端用 ffmpeg 探测后转 16kHz mono PCM 再喂给引擎）
- **采样率 / 声道数**：任意，服务端自动重采样 / 降混
- **时长**：单次建议 < 10 分钟（更长的会被 VAD 切成多段处理，总时间线性增长）
- **大小**：实测 < 50 MB 的文件都能处理（multipart 内存限制 ~100 MB）
- **不支持流式**：必须传完整文件；如需边录边转，自己按段切（建议每段 5-30s）然后并发请求

### 错误码

| HTTP | 含义 | 客户端处理建议 |
| --- | --- | --- |
| 200 | 成功 | — |
| 400 | 请求格式错（缺 file / 缺 model） | 检查 multipart 字段名和必填项 |
| 422 | Pydantic 校验失败 | 同上 |
| 500 | 服务端异常（模型加载失败 / ffmpeg 解析失败） | 重试一次；持续失败联系服务维护方 |
| 503 | 模型尚未就绪（启动期） | 退避 1-2s 重试 |

错误响应体：

```json
{"error": {"message": "ffmpeg not in PATH; cannot preprocess non-16kHz audio", "type": "internal_error", "param": null, "code": null}}
```

### 健康检查

集成进项目时建议先用 `/health` 探活：

```bash
curl http://JiangdeMac-mini.local:8170/health
# {"status":"ok","model":".../ggml-large-v3.bin","n_threads":0,"vad":true,"vad_model":".../ggml-silero-v5.1.2.bin","backend":"pywhispercpp"}
```

`status` 为 `ok` 才表示服务可用且模型已加载；启动期会返回 `loading`。

### 调用方注意事项

1. **mDNS 不可靠**：Windows 没装 Bonjour / 某些 Linux 发行版解析不到 `.local`。生产用法先用 `ping JiangdeMac-mini.local` 验证，失败就 ping Mac mini 的内网 IP。建议在客户端代码里做一次 fallback：

   ```python
   import socket
   for host in ("JiangdeMac-mini.local", "192.168.x.x"):  # 填实际 IP
       try:
           socket.getaddrinfo(host, 8170)
           BASE = f"http://{host}:8170/v1"
           break
       except socket.gaierror:
           continue
   ```

2. **重启感知**：launchd 崩溃后 10s 自动拉起（看 `ThrottleInterval`）；客户端做重试，不要把单次 5xx 当成永久失败。

3. **网络隔离**：服务只暴露在 LAN，**不要把 8170 端口转发到公网**——无鉴权。

4. **大文件分片**：超过 5 分钟的音频自己按静音段切，多次请求拼回；并发请求会顺序处理，分片本身不提速但能让单次失败不丢全段。

5. **语言参数**：传 `language` 显式指定比自动检测快 ~0.3s，且对中英混杂音频效果更好（自动检测倾向输出整段同语种）。

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