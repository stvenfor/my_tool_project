# 内容工具 monorepo

业务代码在 `modules/<biz>/`，公共能力在 `modules/shared/`。根目录 `package.json` 只做 workspaces 与 npm 脚本别名。

## 模块索引

| 模块 | 说明 | 产物目录 |
|------|------|----------|
| [@tools/video-factory](../modules/video-factory/) | 统一编排（narration / dialogue / talking_head） | `modules/video-factory/work/` |
| [@tools/cognitive-video](../modules/cognitive-video/) | 认知解说口播 | `modules/cognitive-video/work/` |
| [@tools/viral-english-dub](../modules/viral-english-dub/) | 病毒片英配 | `modules/viral-english-dub/work/` |
| [@tools/cffex-daily](../modules/cffex-daily/) | 中金所持仓日报 | `modules/cffex-daily/work/` |
| [@tools/city-healing-video](../modules/city-healing-video/) | 城市治愈口播 | `modules/city-healing-video/work/` |
| [@tools/city-bilingual-video](../modules/city-bilingual-video/) | 城市双语 | `modules/city-bilingual-video/work/` |
| [@tools/beat-montage](../modules/beat-montage/) | 踩点混剪 | `modules/beat-montage/work/` |
| [@tools/q-replace](../modules/q-replace/) | 角色替换 / 出镜 | `modules/q-replace/work/` |
| [@tools/dance-remake](../modules/dance-remake/) | 舞蹈翻拍 | `modules/dance-remake/work/` |
| [@tools/three-kingdoms-english-video](../modules/three-kingdoms-english-video/) | 三国英配叙事 | `modules/three-kingdoms-english-video/work/` |
| [@tools/hot-topic-infographic](../modules/hot-topic-infographic/) | 热点信息图 | `modules/hot-topic-infographic/work/` |
| [@tools/cat-drama-video](../modules/cat-drama-video/) | 猫短剧对白 | `modules/cat-drama-video/work/` |
| [@tools/shared-douyin](../modules/shared/douyin/) | 抖音登录 / 发布 | — |
| [@tools/shared-media](../modules/shared/media/) | 参考片切片工具 | — |

## 边界规则

1. 业务模块之间禁止 `sys.path` 互相 import 源码。
2. `video-factory` 可通过 **CLI** 编排兄弟模块。
3. 抖音发布一律走 `modules/shared/douyin`。

## 常用命令

```bash
npm run viral-dub:pipeline -- --config modules/viral-english-dub/work/organ-donate-dog/config.json
npm run cognitive:pipeline -- --id middle-class-exit
npm run video-factory:pipeline -- --id middle-class-exit
npm run cffex:daily
```

## 文档

| 文档 | 说明 |
|------|------|
| [CFFEX 日报视频](cffex-daily-video.md) | 持仓日报流程（路径已迁到 `modules/cffex-daily`） |
| [器官捐献英配链路](../modules/viral-english-dub/docs/organ-donate-dog-pipeline.md) | viral-english-dub 样例 |
