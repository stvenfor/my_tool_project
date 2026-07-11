# 项目文档

| 文档 | 说明 |
|------|------|
| [CFFEX 日报视频完整流程](cffex-daily-video.md) | 从中金所抓数据 → 生成报告图/视频 → 发布抖音 |

## 快速开始

```bash
# 首次安装（见文档「环境准备」）
pip3 install Pillow playwright
cd scripts/cffex-daily/remotion && npm install
npm run cffex:setup-douyin
npm run cffex:auth

# 日常使用
npm run cffex:daily      # 生成今日报告视频
npm run cffex:publish    # 发布到抖音
```
