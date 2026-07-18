# cffex-daily

CFFEX 中信期货净持仓日报：底图 / 视频 / gpt-image-2 美化图文 / 21:00 定时发布。

Work: `modules/cffex-daily/work/`  
Skill: `.cursor/skills/cffex-daily-video/`

```bash
npm run cffex:daily -- --date YYYYMMDD
npm run cffex:beautify -- --date YYYYMMDD
npm run cffex:publish-imagetext -- --date YYYYMMDD --image path/to/beautified.png
npm run cffex:pipeline          # 生成→美化→图文（同定时逻辑）
npm run cffex:schedule          # 安装每晚 21:00
npm run cffex:unschedule
npm run cffex:auto-off          # 停止自动发送
npm run cffex:auto-on
```
