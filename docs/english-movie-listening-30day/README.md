# 30 天四六级词句（10× 扩容）

## 朗读播放（推荐）

用浏览器打开：

**[`player/index.html`](player/index.html)**

- 单词 / 短语 / 句子末列为 **播放 / 暂停**
- 系统语音朗读英文（Web Speech，无需联网音频）
- 建议 Chrome / Safari / Edge

重新生成播放页：`python3 gen_player_html.py`

---

入口目录：[`daily-vocab-30day.md`](daily-vocab-30day.md)

## 每天份量

| 项目 | 数量 |
|------|------|
| 单词（含国际音标） | **80** |
| 短语（含音标） | **40** |
| 不同类型句子 | **30** |
| 词根词缀 | 每组主题若干 |

合计约 **2400 词 + 1200 短语 + 900 句型例句**。

## 文件结构

- [`player/`](player/) — **可点击播放** 的 HTML 学习页
- [`by-day/day-01.md`](by-day/day-01.md) … [`day-30.md`](by-day/day-30.md) — 每日文本备份
- [`bank/`](bank/) — 生成用源数据（`dayNN.txt`）
- [`daily-vocab-30day.md`](daily-vocab-30day.md) — 总目录

## 学法

每天约 **90–120 分钟**（可拆早 40 词 + 晚 40 词）：打开当日 HTML → 点播放跟读 → 英译中 → 中译英 → 短语/句型；睡前复习昨天约 20 词。
