# 批量「四件套」讽刺图文流水线（9:16 动态布局）

LLM 草稿 → 人工审核 → **per-topic 9:16 layout** → AI 底图（可选）→ Pillow 叠字 → 单张长图 + 轮播 5 张。

## 快速命令

| 步骤 | 命令 |
|------|------|
| 安装依赖 | `pip3 install -r scripts/hot-topic-infographic/requirements.txt` |
| 生成草稿 | `npm run infographic:draft -- --keywords "热点1,热点2" --theme "主题" --id topic-id` |
| **批量话题** | `npm run infographic:batch-draft -- --categories worker,family --count 3` |
| 审核通过 | `npm run infographic:approve -- --id topic-id` |
| **生成 layout** | `npm run infographic:layout -- --id topic-id` |
| 校验 layout | `npm run infographic:validate-layout -- --id topic-id` |
| 单条全流程 | `npm run infographic:one -- --id ai-poverty-2026 --template-only` |
| 批量出图 | `npm run infographic:batch -- --template-only --force` |
| 仅长图 | `npm run infographic:batch -- --skip-carousel --template-only` |
| 仅轮播 | `npm run infographic:batch -- --carousel-only --template-only` |
| AI 底图 | `OPENAI_API_KEY=... npm run infographic:base -- --id topic-id --mode both` |
| 导出文案 | `npm run infographic:export -- --all` |
| **迁移 Codex 原图** | `npm run infographic:migrate-uploads -- --id topic-id --source /path/to/codex/dir` |
| **初始化 upload-images** | `npm run infographic:migrate-uploads -- --init-from-categories` |
| 每个 label 生成一张样图 | `npm run infographic:category-previews -- --force` |
| 获取下一张未发送话题图 | `npm run infographic:send-next` |
| 成功发送后按 id 标记 | `npm run infographic:mark-sent -- worker-overtime-burnout-2026` |
| 按 label/id 生成全部话题图 | `npm run infographic:topic-images` |
| 获取下一张未发送话题图 | `npm run infographic:topic-send-next` |
| 查看发送队列统计 | `npm run infographic:send-status` |
| 标记话题图已发送 | `npm run infographic:topic-mark-sent -- <id> --label "打工人"` |

## 输出规格（9:16）

| 产物 | 尺寸 | 路径 |
|------|------|------|
| 单张长图 | 1080×1920 | `_hot-topic-infographic/{id}/output/final.png` |
| 轮播封面 | 1080×1920 | `.../output/carousel/00-cover.png` |
| 轮播四格 | 1080×1920 ×4 | `.../carousel/01.png` ~ `04.png` |
| 布局 | JSON | `_hot-topic-infographic/{id}/layout.json` |

## 动态布局（非固定模板）

每条话题独立 `layout.json`，`style_variant` 三选一：

- `grid_2x2_compact` — 2×2 紧凑网格
- `vertical_stack` — 竖排 4 格
- `staggered_cards` — 交错 2×2

指定 variant：

```bash
npm run infographic:layout -- --id ai-poverty-2026 --variant vertical_stack
```

默认按 topic id 哈希自动分配 variant，保证批量话题版式不同。

## 批量话题（按身份/关系类别）

10 类人群预置在 [`config/categories.json`](config/categories.json)：

打工人、家庭关系、同学关系、朋友关系、钓鱼人、股市交易者、基金玩家、饭搭子、酒友、游戏队友。

每类 `min_topics: 3`，试点类别在 `pilot_topics` 中预置种子（id / angle / keywords / card_hints）。

```bash
# 试点：打工人 + 家庭关系，各 3 条
npm run infographic:batch-draft -- --categories worker,family --count 3

# 后续全量（仅 status 非 pending 或有 pilot_topics 的类别）
npm run infographic:batch-draft -- --all --count 3

# 无 API Key 时用模板兜底
npm run infographic:batch-draft -- --categories worker,family --no-llm
```

产出：

- `topics/draft/{id}.json` — 待审核草稿
- `topics/batch-report-{date}.md` — 生成汇总（成功/失败/跳过）
- 校验失败时额外写入 `{id}_INVALID.json`

每条 topic 的 `meta` 含 `category`（类别 slug）、`angle`（切入角度）、`framing`（内容框架），便于 Codex 批量出图时理解语境。

### 批量话题 → 出图流程

```
1. infographic:batch-draft  → topics/draft/*.json
2. 人工审核文案（看 batch-report）
3. infographic:approve      → topics/approved/*.json
4. 导入 Codex / 本地跑 infographic:one 或 infographic:batch 出图
```

扩展新类别：在 `categories.json` 添加条目，设置 `status: "active"` 并填写 `pilot_topics` 或 `angles`。

## upload-images 工作目录（Codex 原图）

每个 `topic_id` 拥有独立的 `upload-images/` 工作目录，用于存放 Codex 或人工导入的原始图片。目录名固定为 `upload-images`（配置项 `upload_images_subdir`）。

```bash
# 将 Codex 生成目录复制到某话题 upload-images（保留源文件）
npm run infographic:migrate-uploads -- \
  --id workplace-taboo-2026 \
  --source /Users/mac/.codex/generated_images/019f549f-0367-72d2-a885-db7ba5a8764b

# 为 categories.json 全部 topic_id 预创建 upload-images 空目录
npm run infographic:migrate-uploads -- --init-from-categories
```

约定：

- **工作目录**：`_hot-topic-infographic/{topic_id}/upload-images/` — Codex 原图暂存、人工挑选
- **流水线输入**：`base.png`、`carousel/base-*.png` — 选定底图后手动或通过 compose 使用
- **类别预览**：`category-previews/{slug}/` — 按类别 label 的样图，与 upload-images 无关

```
_hot-topic-infographic/{topic_id}/
├── upload-images/          # Codex 原始图工作区
│   ├── exec-*.png
│   └── manifest.json
├── base.png                # 选定底图（流水线用）
├── carousel/base-00.png ... base-04.png
├── output/final.png
└── copy/douyin.json
```

### 分类样图与发送去重

`category_previews.py` 会遍历 `categories.json`，每个不同 `label` 只生成一张样图。图片默认按分类 key 存放；可在分类配置中添加 `storage_key` 覆盖目录名：

```
_hot-topic-infographic/category-previews/{storage_key}/preview.png
_hot-topic-infographic/category-previews/manifest.json
```

此目录只用于每个 label 的视觉预览，不进入定时发送队列。

话题级批量图片位于 `_hot-topic-infographic/category-topics/{storage_key}/{id}/final.png`。这里的 `manifest.json` 是定时发送的唯一状态源，使用 `label + id` 作为唯一键：已有图片默认跳过，新增 id 自动补图，发送成功后才执行 `infographic:mark-sent -- <id>`；已标记 `sent: true` 的图片之后不会再次出队。没有显式 id 的 `angles` 会生成稳定的 `{category}-{序号}-2026` id，直至满足 `min_topics`。

## 工作流

```
1. infographic:draft     → topics/draft/{id}.json
2. 人工审核文案
3. infographic:approve   → topics/approved/{id}.json
4. infographic:layout      → _hot-topic-infographic/{id}/layout.json
5. 人工审核 layout（可选）
6. infographic:validate-layout
7. infographic:base        → base.png + carousel/base-*.png（需 OPENAI_API_KEY）
8. infographic:compose     → final.png + carousel/*.png
9. infographic:export      → douyin.json（5 图轮播）+ xiaohongshu.md
10. 发布
```

## API 成本开关

| 开关 | 效果 |
|------|------|
| `--template-only` | 跳过 AI，PIL 程序化背景 + 叠字 |
| `--skip-base` | 不调用 Images API |
| `--skip-carousel` | 只出单张长图 |
| `--carousel-only` | 只出 5 张轮播 |
| `--force` | 覆盖已有产物 |

单条完整 AI 成本：1 张长图底图 + 5 张轮播底图 ≈ 6 次 Images API 调用。

## 人工审核清单

- [ ] 四格同一主题、有递进
- [ ] 价格/产品名合理（可讽刺不造谣）
- [ ] `infographic:validate` + `infographic:validate-layout` 通过
- [ ] hooks 能引发评论
- [ ] 长图 + 轮播中文可读

## 已内置话题（9:16 试点）

| id | layout variant |
|----|----------------|
| ai-poverty-2026 | grid_2x2_compact |
| chatbot-shutdown-2026 | vertical_stack |
| apple-openai-lawsuit | staggered_cards |

## 抖音发布

轮播模式 `douyin.json` 含 5 张图片路径：

```bash
node ~/.cursor/skills/douyin-image-publish/scripts/publish-imagetext.mjs \
  _hot-topic-infographic/ai-poverty-2026/copy/douyin.json
```

## 目录结构

```
scripts/hot-topic-infographic/
├── config/categories.json    # 10 类身份/关系话题配置
├── schema/topic.schema.json
├── schema/layout.schema.json
├── templates/prompt-base.txt
├── templates/prompt-carousel.txt
├── lib/
│   ├── topic_llm.py            # 共享 LLM 话题生成
│   ├── batch_generate_topics.py
│   ├── migrate_upload_images.py
│   ├── generate_layout.py    # per-topic 9:16 layout
│   ├── validate_layout.py
│   ├── compose.py            # --mode single|carousel|both
│   ├── generate_base.py      # --mode single|carousel|both
│   └── batch_run.py
├── topics/draft/
└── topics/approved/

_hot-topic-infographic/{id}/
├── upload-images/            # Codex 原图工作区
│   ├── exec-*.png
│   └── manifest.json
├── topic.json
├── layout.json               # 每条独有
├── base.png
├── carousel/base-00.png ... base-04.png
├── output/final.png
├── output/carousel/00-cover.png ... 04.png
└── copy/douyin.json
```
