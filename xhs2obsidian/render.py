"""生成和更新单篇 Obsidian 笔记的 Markdown。"""
from __future__ import annotations

import datetime
import re

_INLINE_TAG = re.compile(r"#([^#\s\[]+)")
_TOPIC_MARK = re.compile(r"#[^#\s\[]+(?:\[话题\])?#?")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F"
    "\U000024C2\U0000200D\U000020E3]+"
)
_FILENAME = str.maketrans({
    "/": "-", "\\": "-", ":": "：", "|": "｜", "?": "？",
    "*": "", '"': "", "<": "", ">": "", "#": "", "^": "", "[": "", "]": "",
})

OCR_HEADING = "图片文字（OCR 提取）"
TRANSCRIPT_HEADING = "视频转录"
MEDIA_HEADINGS = (OCR_HEADING, TRANSCRIPT_HEADING)


# ---------- 小工具 ----------

def topic_label(topic: str) -> str:
    """"03 科研与PhD" → "科研与PhD"。"""
    return re.sub(r"^\d+\s+", "", topic).strip() or topic


def all_tags(note) -> list[str]:
    """「作品标签」字段 ∪ 正文里的 #话题#。字段经常缺项，所以两边都收。"""
    return list(dict.fromkeys(note.tags.split() + _INLINE_TAG.findall(note.desc)))


def has_prose(note) -> bool:
    """去掉 #话题# 后还剩 10 个字以上，才算有文字正文。"""
    return len(_TOPIC_MARK.sub(" ", note.desc).strip()) >= 10


def derive_title(note) -> str:
    """标题为空时，用正文第一句；再没有就用标签。不编造内容。"""
    if note.title.strip():
        return note.title.strip()
    body = re.sub(r"[ \t]+", " ", _TOPIC_MARK.sub(" ", note.desc))
    for line in body.split("\n"):
        line = line.strip()
        if len(line) < 4:
            continue
        seg = re.split(r"[。！？；]", line)[0].strip()
        if len(seg) > 30:
            seg = re.split(r"[，、]", seg)[0].strip()
        return (seg or line)[:30]
    tags = note.tags.split()
    if tags:
        return "、".join(tags[:3])
    return f"{note.author or '未知作者'} 的收藏"


def safe_name(s: str, limit: int = 70) -> str:
    s = _EMOJI.sub("", s or "").translate(_FILENAME)
    s = re.sub(r"\s+", " ", s).strip().strip("。，、；！？ .")
    return s[:limit].strip() or "无标题"


def yaml_str(s: str) -> str:
    s = re.sub(r"\s*\n\s*", " ", s or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def num(v: str) -> int | None:
    """解析互动数量："1.4万" / "2千" / "311"；-1 或空表示小红书未公开。"""
    m = re.fullmatch(r"(-?[\d.]+)\s*([万千])?", (v or "").strip())
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    n *= {"万": 10000, "千": 1000}.get(m.group(2) or "", 1)
    n = int(round(n))
    return None if n < 0 else n


def show_raw(v: str) -> str:
    v = (v or "").strip()
    return "未公开" if v in ("", "-1") else v


def code_block(text: str) -> list[str]:
    """把原样文字放进代码块。围栏比内容里最长的反引号串多一个，不会被内容提前闭合。"""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence + "text", text.rstrip("\n"), fence]


# ---------- 媒体小节 ----------

def media_lines(ocr: list[tuple[int, str]], transcripts: list[dict]) -> list[str]:
    """「图片文字」和「视频转录」两个小节。ocr = [(图序号, 文字)]，transcripts = [{text, model, duration}]。"""
    out: list[str] = []
    ocr = [(i, t) for i, t in ocr if t.strip()]
    transcripts = [t for t in transcripts if t.get("text", "").strip()]
    if ocr:
        out += [f"## {OCR_HEADING}", "",
                f"> [!note] 以下文字由 macOS Vision OCR 从 {len(ocr)} 张图片中自动识别，"
                "**可能有错字或漏字**，性质上不同于上方的作者原文。图片本身未存入库中。", ""]
        for i, t in ocr:
            out += [f"### 图 {i}", "", *code_block(t.strip()), ""]
    if transcripts:
        out += [f"## {TRANSCRIPT_HEADING}", ""]
        for k, tr in enumerate(transcripts, 1):
            if len(transcripts) > 1:
                out += [f"### 视频 {k}", ""]
            out += [f"> [!note] 由 Whisper 自动语音转录（模型 {tr.get('model', '?')}，"
                    f"时长 {tr.get('duration', '?')}），**可能有听错或漏句**，不是作者原文。", "",
                    *code_block(tr["text"].strip()), ""]
    return out


# ---------- 新建笔记 ----------

def build_note(note, topic: str, ocr, transcripts, scaffold: bool = True,
               today: str | None = None) -> str:
    today = today or datetime.date.today().isoformat()
    label = topic_label(topic)
    title = derive_title(note)
    tags = all_tags(note)
    url = note.url or f"https://www.xiaohongshu.com/explore/{note.nid}"
    url_note = "" if note.url else "（通用链接，可能需要登录才能打开）"
    n_ocr = sum(1 for _, t in ocr if t.strip())
    has_tr = any(t.get("text", "").strip() for t in transcripts)
    media = note.media or "未知"

    fm = ["---", "type: source", "status: inbox", "platform: 小红书",
          f"media: {media}", f"topic: {label}",
          f"title: {yaml_str(title)}", f"author: {yaml_str(note.author)}",
          f"author-url: {note.aurl}", f"url: {url}", f"note-id: {yaml_str(note.nid)}",
          f"published: {note.pub.split('_')[0]}",
          f"collected: {(note.saved or today).split(' ')[0]}"]
    for key, raw in (("likes", note.lik), ("collects", note.fav),
                     ("comments", note.cmt), ("shares", note.shr)):
        v = num(raw)
        fm.append(f"{key}: {'' if v is None else v}")
    if n_ocr:
        fm.append(f"ocr-images: {n_ocr}")
    if has_tr:
        fm.append("transcript: true")
    fm += ["tags:", "  - source/xiaohongshu", f"  - topic/{label}", f"  - media/{media}"]
    if tags:
        fm += ["xhs-tags:", *(f"  - {yaml_str(t)}" for t in tags)]
    fm.append("---")

    author = f"[{note.author}]({note.aurl})" if note.aurl else (note.author or "未知")
    b = ["", "", f"# {title}", "", "## 来源信息", "",
         f"- 类型：{media}（小红书）",
         f"- 作者：{author}",
         f"- 原文链接：[在小红书打开]({url}){url_note}",
         f"- 发布时间：{note.pub.replace('_', ' ')}",
         f"- 采集时间：{note.saved}",
         f"- 互动数据：❤️ 点赞 {show_raw(note.lik)} ｜ ⭐ 收藏 {show_raw(note.fav)} ｜ "
         f"💬 评论 {show_raw(note.cmt)} ｜ 🔗 分享 {show_raw(note.shr)}",
         "", "## 原文", ""]
    if not note.desc.strip():
        b += ["> [!warning] 采集到的作品描述为空，作者没有写文字正文。"
              "内容在图片或视频里，见下方提取的文字，或打开原文链接查看。", ""]
    else:
        tip = ("> [!info] 以下为采集原文，逐字未改。"
               "用代码块是为了避免正文里的 `#话题#` 被 Obsidian 解析成标签。")
        b += [tip, "", *code_block(note.desc), ""]
    b += media_lines(ocr, transcripts)
    if tags:
        b += ["## 原始话题标签", "", "、".join(tags), "",
              "> 已完整保留在 frontmatter 的 `xhs-tags` 属性中（作品标签字段 ∪ 正文内联标签）。", ""]
    if scaffold:
        b += ["## 我的理解", "", "", "## 相关概念", "", "- ", "", "## 下一步行动", "", "- [ ] ", ""]
    return "\n".join(fm) + "\n".join(b)


# ---------- 更新已有笔记 ----------

def _h2_outside_code(lines: list[str]):
    """逐行给出 (行, 所在二级标题, 本行是否就是标题)。代码块里的 "## " 不算标题。"""
    fence, heading = 0, None
    for ln in lines:
        is_head = not fence and ln.startswith("## ")
        if is_head:
            heading = ln[3:].strip()
        m = re.match(r"^(`{3,})(.*)$", ln)
        if m:
            if not fence:
                fence = len(m.group(1))
            elif len(m.group(1)) >= fence and not m.group(2).strip():
                fence = 0
        yield ln, heading, is_head


def update_note(text: str, ocr, transcripts) -> str:
    """只替换「图片文字」「视频转录」两个小节和对应的 frontmatter 字段，其余内容（包括你写的笔记）不动。"""
    lines = [ln for ln, h, _ in _h2_outside_code(text.split("\n")) if h not in MEDIA_HEADINGS]

    headings = [(i, h) for i, (_, h, is_head) in enumerate(_h2_outside_code(lines)) if is_head]
    anchor = next((i for want in ("原始话题标签", "我的理解") for i, h in headings if h == want), None)
    new = media_lines(ocr, transcripts)
    if new:
        if anchor is None:
            if lines and lines[-1] != "":
                lines.append("")
            lines += new
        else:
            lines[anchor:anchor] = new

    # frontmatter：ocr-images / transcript 放在 tags: 前面
    if lines and lines[0] == "---" and "---" in lines[1:]:
        end = lines.index("---", 1)
        fm = [ln for ln in lines[1:end] if not ln.startswith(("ocr-images:", "transcript:"))]
        n_ocr = sum(1 for _, t in ocr if t.strip())
        add = ([f"ocr-images: {n_ocr}"] if n_ocr else []) + \
              (["transcript: true"] if any(t.get("text", "").strip() for t in transcripts) else [])
        pos = fm.index("tags:") if "tags:" in fm else len(fm)
        fm[pos:pos] = add
        lines = ["---", *fm, *lines[end:]]
    return "\n".join(lines)
