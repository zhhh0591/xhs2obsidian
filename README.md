# xhs2obsidian

把小红书上收藏的作品变成 Obsidian 笔记。一条命令完成：

```
小红书链接 ──下载──▶ 文字 / 图片 / 视频 ──OCR / 转录──▶ Obsidian 笔记 + 收藏地图
```

- **下载**：内置 [XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader)（最新 master 源码），支持作品链接、分享文案和短链
- **图片 OCR**：用 macOS 自带的 Vision 识别图片里的文字，完全离线
- **视频转录**：用 [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) 在本机转写，不上传任何音视频
- **生成笔记**：每篇一个 Markdown，带 frontmatter（作者、链接、互动数据、话题标签……），按主题分文件夹
- **收藏地图**：自动生成一个总索引，按主题列表、按收藏数排序
- **可以反复运行**：OCR 和转录结果有缓存，只处理新增的；已导入的笔记只更新提取出的文字，你自己写的内容和手动挪过的文件夹都不会被动

## 环境要求

| 功能 | 要求 |
|---|---|
| 下载、生成笔记 | Python 3.12+，任何系统 |
| 图片 OCR | macOS |
| 视频转录 | macOS + Apple Silicon（M 系列芯片） |

OCR 和转录可以在配置里关掉，其余功能照常可用。

## 安装

```bash
git clone https://github.com/zhhh0591/xhs2obsidian.git
cd xhs2obsidian
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml
```

然后打开 `config.toml`，至少改两个路径：

```toml
[paths]
download_dir = "~/Documents/小红书下载"     # 下载的文件放哪
vault = "~/Documents/Obsidian/MyVault"     # 你的 Obsidian 库
```

## 使用

```bash
# 下载几篇作品并整理进 Obsidian（链接可以写多个）
python -m xhs2obsidian run "https://www.xiaohongshu.com/explore/xxxx?xsec_token=xxxx"

# 链接很多时，放进文本文件，一行一个（直接粘贴分享文案也行）
python -m xhs2obsidian run -f links.txt

# 不给链接：只处理下载目录里已有的内容
python -m xhs2obsidian run
```

第一次转录视频时会自动下载 Whisper 模型。默认按内存自动选：16GB 及以上用完整版 large-v3-turbo（1.6GB，运行时约占 3.5GB 内存）；8GB 的 Mac 用 4-bit 量化版（464MB，约占 1.2GB），中文转录和完整版的字符相似度实测约 97%。

**想把自己的收藏 / 点赞全部导出？** 用 XHS-Downloader 自带的浏览器用户脚本（需要 Tampermonkey），
它能在收藏页、点赞页批量提取作品链接，存成 `links.txt` 后交给 `run -f`。
用户脚本的安装方法见 [XHS-Downloader 的说明](XHS-Downloader/README.md#user-scripts)。

### 全部命令

| 命令 | 作用 |
|---|---|
| `run [链接…] [-f 文件]` | 下载 → OCR → 转录 → 写笔记 → 重建索引 |
| `fetch [链接…] [-f 文件]` | 只下载 |
| `scan` | 只统计：有几篇、几张图、几个视频、会分到哪些主题。不写任何文件 |
| `ocr` / `transcribe` | 只做 OCR / 只做转录 |
| `build` | 只新建 / 更新笔记 |
| `index` | 只重建收藏地图和 README |

全局参数：`-c 配置文件`（默认 `./config.toml`）、`--vault 路径`（临时换一个库，适合先输出到空文件夹试跑）。

## 生成的笔记长什么样

```markdown
---
type: source
status: inbox
platform: 小红书
media: 图文
topic: 科研与PhD
title: "示例：我的论文阅读流程"
author: "某作者"
url: https://www.xiaohongshu.com/discovery/item/...?xsec_token=...
note-id: "..."
published: 2026-01-01
likes: 120
collects: 300
ocr-images: 3
tags:
  - source/xiaohongshu
  - topic/科研与PhD
  - media/图文
xhs-tags:
  - "论文阅读"
  - "研究生"
---

# 示例：我的论文阅读流程

## 来源信息        作者、原文链接、发布时间、互动数据
## 原文            作者写的正文，逐字保留
## 图片文字（OCR 提取）   每张图一段
## 视频转录
## 原始话题标签
## 我的理解        ← 留给你写
## 相关概念
## 下一步行动
```

几个刻意的设计：

- **原文和提取的文字都放在代码块里。** 小红书正文末尾常带一串 `#话题#`，直接写进正文会被 Obsidian 当成标签，几十篇就能把标签面板冲垮。话题另存进 `xhs-tags` 属性，照样能搜。
- **机器提取的文字明确标注。** OCR 和转录可能有错字，笔记里和作者原文分开放，并注明来源。
- **话题标签取并集。** 「作品标签」字段经常和正文里的 `#话题#` 对不上，两边都收，不丢信息。
- **没有文字的作品默认不导入。** 正文只有话题标签、图片和视频里也提取不到字的，导进来只是空壳（`skip_empty` 可关）。

## 主题分类

新笔记按 `config.toml` 里的关键词自动分到子文件夹：标题命中 3 分、标签 2 分、正文 1 分，取最高分；都不命中归入 `99 未分类`。也可以按作品 ID 手动指定：

```toml
[topics.keywords]
"03 科研与PhD" = ["科研", "论文", "PhD", "博士"]
"07 英语学习" = ["英语", "雅思", "外刊"]

[topics.overrides]
"作品ID" = "03 科研与PhD"
```

分类只在第一次导入时发生。之后你在 Obsidian 里把笔记拖到别的文件夹，再运行也不会被挪回去。

## Cookie 与隐私

- 不填 Cookie 也能下载大部分公开作品。需要时用环境变量传入，不要写进会提交的文件：

  ```bash
  export XHS_COOKIE='你的小红书网页版 Cookie'
  ```

- `config.toml`、下载目录、缓存、`XHS-Downloader/Volume/` 都已写进 `.gitignore`。
- OCR 和转录都在本机完成，图片、视频、文字不会发给任何服务器。

## 关于内置的 XHS-Downloader

`XHS-Downloader/` 目录是 [JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) 的源码，用 `git subtree` 原样引入，没有改动。它本身也能单独使用（终端界面、图形界面、API、MCP 都有）：

```bash
cd XHS-Downloader
python main.py
```

同步上游的最新代码：

```bash
git subtree pull --prefix=XHS-Downloader https://github.com/JoeanAmier/XHS-Downloader master --squash
```

## 测试

```bash
python -m unittest
```

测试只用虚构数据，不联网。

## 许可证

[GPL-3.0](LICENSE)。本仓库包含 XHS-Downloader（GPL-3.0，© JoeanAmier）的源码，因此整体按 GPL-3.0 发布。`xhs2obsidian/` 目录下的转换代码 © 2026 zhhh0591。

## 免责声明

本项目只用于整理自己收藏的内容、个人学习和研究。

- 下载的作品版权归原作者所有，请勿二次发布、商用或公开传播。
- 使用时请遵守小红书的用户协议和当地法律法规，控制请求频率，不要批量采集他人数据。
- 下载功能来自 XHS-Downloader，使用前请同时阅读并接受[它的免责声明](XHS-Downloader/README.md)。
- 因使用本项目产生的任何后果由使用者自行承担。
