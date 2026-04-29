# bilibili2article：b站视频转文字工具

一个用于 **b站视频转文字** 的本地工具：输入 Bilibili 视频链接，优先读取官方字幕；如果视频没有开放字幕，则下载当前账号可播放的媒体流，并用本地 `faster-whisper` 语音识别生成 Markdown 逐字稿。

适合用来把 B 站长视频、课程、访谈、财经分析等内容转成可检索、可整理的文字稿。

## 功能

- 支持 `BV` 号或完整 Bilibili URL。
- 优先使用 Bilibili 官方字幕/AI 字幕。
- 官方字幕不可用时，自动回退到本地 ASR 语音识别。
- 支持多 P 视频，URL 带 `?p=2` 时只处理指定分 P。
- 支持批量转写本地视频文件夹。
- 输出 Markdown 文件，便于继续整理成文章或笔记。

## 本地安装

先把仓库下载到本地：

```bash
git clone https://github.com/Elaineyex/bilibili2article.git
cd bilibili2article
```

建议使用 Python 3.12。语音识别相关依赖在较新的 Python 版本上可能没有完整 wheel。

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -r requirements.txt
```

如果本机没有 `python3.12`，请先用 Homebrew、uv、pyenv 或其他 Python 管理工具安装 Python 3.12。

## 登录 Bilibili

部分视频、字幕接口和会员/充电内容需要登录态。

```bash
source .venv312/bin/activate
python refresh_env.py
```

终端会显示二维码，用 Bilibili 手机 App 扫码登录。登录成功后，cookies 会写入 `.env`。`.env` 已被 `.gitignore` 忽略，不要提交到 GitHub。

`.env.example` 列出了支持的 cookie 和 ASR 环境变量。

## 转写 Bilibili 视频

```bash
source .venv312/bin/activate
python convert.py "https://www.bilibili.com/video/BV1hvSKB4EgK/"
```

输出文件：

```text
article_<bvid>.md
```

处理指定分 P：

```bash
python convert.py "https://www.bilibili.com/video/<BV_ID>/?p=2"
```

也可以直接传 BV 号：

```bash
python convert.py "BV1hvSKB4EgK"
```

## 本地 ASR 参数

官方字幕不可用时，会使用 `faster-whisper` 做本地语音识别。默认配置：

- 模型：`medium`
- 语言：`zh`
- 设备：`cpu`
- 计算类型：`int8`

可以用环境变量覆盖：

```bash
BILI_ASR_MODEL=small BILI_ASR_LANGUAGE=zh python convert.py "<bilibili-url>"
```

指定媒体缓存目录：

```bash
BILI_ASR_CACHE_DIR=./asr_cache python convert.py "<bilibili-url>"
```

下载的视频/音频只是缓存，转写完成后可以删除。

## 转写本地单个视频

如果你已经手动下载了视频，可以直接转写本地文件：

```bash
source .venv312/bin/activate

.venv312/bin/python - <<'PY'
from pathlib import Path
from convert import transcribe_with_local_asr

video = Path("/full/path/to/video.mp4")
out = Path("local_transcripts") / f"{video.stem}.md"
out.parent.mkdir(exist_ok=True)

text = transcribe_with_local_asr(video)
out.write_text(
    f"# {video.stem}\n\n**Source file:** {video}\n\n---\n\n{text}\n",
    encoding="utf-8",
)
print(f"Saved: {out}")
PY
```

## 批量转写本地视频文件夹

```bash
source .venv312/bin/activate
python transcribe_local_dir.py "/path/to/video-folder" "local_transcripts/output-folder"
```

长任务建议后台运行：

```bash
nohup env BILI_ASR_MODEL=medium BILI_ASR_LANGUAGE=zh \
  .venv312/bin/python transcribe_local_dir.py \
  "/path/to/video-folder" \
  "local_transcripts/output-folder" \
  > transcribe.log 2>&1 &
```

查看进度：

```bash
tail -f transcribe.log
```

批量脚本会跳过已经生成的 `.md` 文件，所以中断后重新运行同一条命令即可继续。

## 常见问题

### 为什么只能转写视频开头一小段？

有些视频是充电专属、会员专属或其他受限内容。即使已经登录，如果当前账号只能播放预览，Bilibili 也只会返回预览媒体流。脚本会检测这种情况并停止，避免生成误导性的半截稿。

解决方法：确认当前登录账号能在 Bilibili 正常播放完整视频，然后重新运行 `python refresh_env.py` 更新 `.env`。

### 这个工具会绕过 Bilibili 权限吗？

不会。它只使用当前登录账号可访问的字幕或媒体流，不绕过 Bilibili 的访问控制。

### 速度很慢怎么办？

CPU 上跑 `medium` 模型会比较慢。可以改用更小模型：

```bash
BILI_ASR_MODEL=small python convert.py "<bilibili-url>"
```

或：

```bash
BILI_ASR_MODEL=tiny python convert.py "<bilibili-url>"
```

模型越小速度越快，但准确率可能下降。

## 输出与隐私

- `.env` 保存登录 cookie，已被 git 忽略。
- `local_transcripts/`、`article_*.md`、视频缓存和日志文件默认不提交。
- 所有 ASR 转写都在本地运行，不需要上传音频到云端。
