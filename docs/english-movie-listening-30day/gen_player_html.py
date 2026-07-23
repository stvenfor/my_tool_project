#!/usr/bin/env python3
"""Generate player HTML pages from bank/dayNN.txt with play/pause buttons."""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BANK = ROOT / "bank"
OUT = ROOT / "player"


def parse_bank(path: Path) -> dict:
    title = path.stem
    roots: list[tuple[str, str, str]] = []
    words: list[tuple[str, str, str, str]] = []
    phrases: list[tuple[str, str, str, str]] = []
    sents: list[tuple[str, str, str]] = []  # type, en, zh

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("#TITLE "):
            title = line[7:].strip()
        elif line.startswith("#ROOT "):
            a, b, c = line[6:].split("|", 2)
            roots.append((a.strip(), b.strip(), c.strip()))
        elif line.startswith("#WORD "):
            a, b, c, d = line[6:].split("|", 3)
            words.append((a.strip(), b.strip(), c.strip(), d.strip()))
        elif line.startswith("#PHRASE "):
            a, b, c, d = line[8:].split("|", 3)
            phrases.append((a.strip(), b.strip(), c.strip(), d.strip()))
        elif line.startswith("#SENT "):
            # n|type|en|zh
            parts = line[6:].split("|", 3)
            if len(parts) == 4:
                _, typ, en, zh = parts
                sents.append((typ.strip(), en.strip(), zh.strip()))
        # skip #SENTTYPE

    return {
        "title": title,
        "roots": roots,
        "words": words,
        "phrases": phrases,
        "sents": sents,
    }


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def speak_btn(text: str) -> str:
    return (
        f'<button type="button" class="speak-btn" data-speak="{esc(text)}" '
        f'aria-label="播放或暂停：{esc(text)}">播放</button>'
    )


def render_day(n: int, data: dict, titles: dict[int, str]) -> str:
    title = data["title"]
    prev_link = (
        f'<a href="day-{n-1:02d}.html">← Day {n-1}</a>' if n > 1 else '<span class="muted">← Day</span>'
    )
    next_link = (
        f'<a href="day-{n+1:02d}.html">Day {n+1} →</a>' if n < 30 else '<span class="muted">Day →</span>'
    )

    root_rows = "\n".join(
        f"<tr><td><strong>{esc(r)}</strong></td><td>{esc(m)}</td><td>{esc(e)}</td></tr>"
        for r, m, e in data["roots"]
    ) or "<tr><td colspan='3' class='muted'>（无）</td></tr>"

    word_rows = []
    for i, (w, ipa, gloss, tip) in enumerate(data["words"], 1):
        word_rows.append(
            "<tr>"
            f'<td class="num">{i}</td>'
            f'<td class="en">{esc(w)}</td>'
            f'<td class="ipa">{esc(ipa)}</td>'
            f"<td>{esc(gloss)}</td>"
            f'<td class="tip">{esc(tip)}</td>'
            f'<td class="play-cell">{speak_btn(w)}</td>'
            "</tr>"
        )

    phrase_rows = []
    for i, (p, ipa, gloss, ex) in enumerate(data["phrases"], 1):
        phrase_rows.append(
            "<tr>"
            f'<td class="num">{i}</td>'
            f'<td class="en">{esc(p)}</td>'
            f'<td class="ipa">{esc(ipa)}</td>'
            f"<td>{esc(gloss)}</td>"
            f"<td>{esc(ex)}</td>"
            f'<td class="play-cell">{speak_btn(p)}</td>'
            "</tr>"
        )

    sent_rows = []
    for i, (typ, en, zh) in enumerate(data["sents"], 1):
        sent_rows.append(
            "<tr>"
            f'<td class="num">{i}</td>'
            f"<td>{esc(typ)}</td>"
            f'<td class="en">{esc(en)}</td>'
            f"<td>{esc(zh)}</td>"
            f'<td class="play-cell">{speak_btn(en)}</td>'
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Day {n} — {esc(title)}</title>
  <link rel="stylesheet" href="assets/player.css" />
</head>
<body>
  <div class="wrap">
    <header class="page-head">
      <h1>Day {n} — {esc(title)}</h1>
      <nav class="nav">
        <a href="index.html">目录</a>
        {prev_link}
        {next_link}
      </nav>
    </header>
    <p class="hint">末列「播放 / 暂停」用浏览器朗读英文（Web Speech，美式优先，语速 0.9）。Markdown 文本备份见 <code>../by-day/day-{n:02d}.md</code>。</p>

    <section class="block">
      <h2>词根词缀</h2>
      <table class="roots">
        <thead><tr><th>成分</th><th>含义</th><th>例词</th></tr></thead>
        <tbody>
{root_rows}
        </tbody>
      </table>
    </section>

    <section class="block">
      <h2>单词（{len(data["words"])}）</h2>
      <table class="grid">
        <thead>
          <tr>
            <th>#</th><th>单词</th><th>音标</th><th>词性/中文</th><th class="tip">词源提示</th><th>播放</th>
          </tr>
        </thead>
        <tbody>
{chr(10).join(word_rows)}
        </tbody>
      </table>
    </section>

    <section class="block">
      <h2>短语（{len(data["phrases"])}）</h2>
      <table class="grid">
        <thead>
          <tr>
            <th>#</th><th>短语</th><th>音标</th><th>中文</th><th>例句</th><th>播放</th>
          </tr>
        </thead>
        <tbody>
{chr(10).join(phrase_rows)}
        </tbody>
      </table>
    </section>

    <section class="block">
      <h2>句型训练（{len(data["sents"])}）</h2>
      <table class="grid">
        <thead>
          <tr>
            <th>#</th><th>句型</th><th>英文句子</th><th>中文</th><th>播放</th>
          </tr>
        </thead>
        <tbody>
{chr(10).join(sent_rows)}
        </tbody>
      </table>
    </section>
  </div>
  <script src="assets/speak.js"></script>
</body>
</html>
"""


def render_index(titles: dict[int, str]) -> str:
    items = []
    for n in range(1, 31):
        t = titles.get(n, f"Day {n}")
        items.append(
            f'<li><a href="day-{n:02d}.html"><span class="day-num">Day {n}</span>{esc(t)}</a></li>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>30 天四六级词表 · 朗读播放</title>
  <link rel="stylesheet" href="assets/player.css" />
</head>
<body>
  <div class="wrap">
    <header class="page-head">
      <h1>30 天四六级词表 · 朗读播放</h1>
    </header>
    <p class="hint">用浏览器打开任意 Day。每行末列可<strong>播放 / 暂停</strong>英文（系统语音，无需联网音频文件）。建议 Chrome / Safari / Edge。</p>
    <ul class="day-list">
{chr(10).join(items)}
    </ul>
  </div>
</body>
</html>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)

    titles: dict[int, str] = {}
    for path in sorted(BANK.glob("day*.txt")):
        m = re.match(r"day(\d+)\.txt$", path.name)
        if not m:
            continue
        n = int(m.group(1))
        data = parse_bank(path)
        titles[n] = data["title"]
        out = OUT / f"day-{n:02d}.html"
        out.write_text(render_day(n, data, titles), encoding="utf-8")
        print(
            f"wrote {out.name} words={len(data['words'])} "
            f"phrases={len(data['phrases'])} sents={len(data['sents'])}"
        )

    index = OUT / "index.html"
    index.write_text(render_index(titles), encoding="utf-8")
    print(f"wrote {index.name} days={len(titles)}")


if __name__ == "__main__":
    main()
