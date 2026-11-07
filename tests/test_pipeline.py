"""用虚构数据测试：解析导出、生成笔记、更新笔记、主题归类。运行：python -m unittest"""
import os
import sqlite3
import tempfile
import unittest

from xhs2obsidian import reader
from xhs2obsidian.config import Config
from xhs2obsidian.render import build_note, derive_title, has_prose, num, update_note
from xhs2obsidian.topics import classify

NID = "0123456789abcdef01234567"
DESC = "第一行正文，讲怎么用 Obsidian 记笔记。\n\t\n第二行有 ``` 三个反引号\n#Obsidian[话题]# #效率[话题]#"

MD = f"""## 📝 作品信息
- **作品ID**：`{NID}`
- **作品类型**：图文
- **发布时间**：2026-01-02_03:04:05
- **最后更新时间**：2026-01-02_03:04:05

---

## 💬 作品内容
- **作品标题**：示例标题
- **作品描述**：
""" + "".join(f"  > {ln}  \n" for ln in DESC.split("\n")) + """- **作品标签**：Obsidian 效率

---

## 📊 互动数据统计
- ❤️ **点赞数量**：1.2万
- ⭐ **收藏数量**：345
- 💬 **评论数量**：-1
- 🔗 **分享数量**：6

---

## 👤 作者信息
- **作者昵称**：示例作者
- **作者ID**：`aaaaaaaaaaaaaaaaaaaaaaaa`
- **作者链接**：https://www.xiaohongshu.com/user/profile/aaaaaaaaaaaaaaaaaaaaaaaa

***保存时间：2026-01-03 10:00***
"""


def make_download_dir(tmp):
    stem = os.path.join(tmp, "2026-01-02_示例作者_示例标题")
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write(MD)
    for i in (2, 1):
        open(f"{stem}_{i}.jpeg", "wb").close()
    open(os.path.join(tmp, "无关图片.png"), "wb").close()
    con = sqlite3.connect(os.path.join(tmp, "ExploreData.db"))
    con.execute("CREATE TABLE explore_data (作品ID TEXT PRIMARY KEY, 作品链接 TEXT, 作品描述 TEXT)")
    con.execute("INSERT INTO explore_data VALUES (?, ?, ?)",
                (NID, f"https://www.xiaohongshu.com/discovery/item/{NID}?xsec_token=TOKEN", DESC))
    con.commit()
    con.close()


class ReaderTest(unittest.TestCase):
    def test_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_download_dir(tmp)
            notes, unmatched = reader.load(tmp)
        n = notes[NID]
        self.assertEqual(n.desc, DESC)  # 逐字还原，包括 tab 行
        self.assertEqual(n.title, "示例标题")
        self.assertEqual(n.saved, "2026-01-03 10:00")
        self.assertIn("xsec_token=TOKEN", n.url)  # md 里没有链接，从 DB 补
        self.assertEqual([i for i, _ in n.images], [1, 2])
        self.assertEqual([os.path.basename(p) for p in unmatched], ["无关图片.png"])


class RenderTest(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_download_dir(tmp)
            self.note = reader.load(tmp)[0][NID]

    def test_numbers(self):
        self.assertEqual(num("1.2万"), 12000)
        self.assertIsNone(num("-1"))
        self.assertIsNone(num(""))

    def test_build_and_update_are_idempotent(self):
        ocr = [(1, "图一的文字"), (2, "")]
        tr = [{"text": "转录内容", "model": "m", "duration": "1分0秒"}]
        md = build_note(self.note, "05 知识管理", ocr, tr, today="2026-01-04")
        self.assertIn("ocr-images: 1\ntranscript: true\ntags:", md)
        self.assertIn("likes: 12000\ncollects: 345\ncomments: \n", md)
        self.assertIn("````text\n" + DESC + "\n````", md)  # 内容里有 ```，围栏自动加长
        self.assertEqual(update_note(md, ocr, tr), md)

    def test_update_keeps_user_text(self):
        md = build_note(self.note, "05 知识管理", [(1, "旧文字")], [], today="2026-01-04")
        md = md.replace("## 我的理解\n\n", "## 我的理解\n\n我自己写的想法\n")
        new = update_note(md, [(1, "新文字"), (2, "第二张")], [])
        self.assertIn("我自己写的想法", new)
        self.assertIn("新文字", new)
        self.assertNotIn("旧文字", new)
        self.assertIn("ocr-images: 2", new)
        self.assertEqual(new.count("## 图片文字（OCR 提取）"), 1)

    def test_update_without_new_text_keeps_old_sections(self):
        tr = [{"text": "旧转录", "model": "m", "duration": "1分0秒"}]
        md = build_note(self.note, "05 知识管理", [(1, "旧文字")], tr, today="2026-01-04")
        self.assertEqual(update_note(md, [], []), md)  # 视频删了、没有新文字：原样保留
        new = update_note(md, [(1, "新文字")], [])  # 只有 OCR 更新，转录保留
        self.assertIn("旧转录", new)
        self.assertIn("新文字", new)
        self.assertLess(new.index("## 图片文字"), new.index("## 视频转录"))
        self.assertIn("ocr-images: 1\ntranscript: true\ntags:", new)

    def test_prose_and_title(self):
        self.assertTrue(has_prose(self.note))
        self.note.title = ""
        self.assertEqual(derive_title(self.note), "第一行正文，讲怎么用 Obsidian 记笔记")


class ModelChoiceTest(unittest.TestCase):
    def test_auto_model(self):
        from xhs2obsidian.transcribe import FULL_MODEL, LIGHT_MODEL, resolve_model
        self.assertEqual(resolve_model("auto", ram_gb=8), LIGHT_MODEL)
        self.assertEqual(resolve_model("", ram_gb=16), FULL_MODEL)
        self.assertEqual(resolve_model("mlx-community/whisper-small-mlx", ram_gb=8),
                         "mlx-community/whisper-small-mlx")  # 手动指定的不改


class TopicTest(unittest.TestCase):
    def test_classify(self):
        cfg = Config(download_dir="", vault="", topic_keywords={
            "01 AI": ["AI"], "02 笔记": ["Obsidian", "笔记"]})
        n = reader.Note(NID, title="Obsidian 笔记法", desc="he said it works")
        self.assertEqual(classify(n, cfg), "02 笔记")  # "said" 不算命中 "AI"
        n2 = reader.Note("x", title="随便看看")
        self.assertEqual(classify(n2, cfg), cfg.topic_default)
        cfg.topic_overrides = {NID: "01 AI"}
        self.assertEqual(classify(n, cfg), "01 AI")


if __name__ == "__main__":
    unittest.main()
