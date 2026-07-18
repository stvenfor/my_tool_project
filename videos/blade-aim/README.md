# 刃与准

灰色近战者「刃」与红色狙击手「准」，对抗无穷白色士兵的三幕火柴人短片。

## 分镜（90s）

| 时间 | 幕 | 内容 |
|------|----|------|
| 0–8s | 片头 / 第一幕 | 城门口 |
| 7.5–21s | 近战 | 盾缝刺击、横划崩裂、刀尖点地 |
| 20.5–32s | 狙击 | 钟楼 · 三连折射 · 五折弹道 |
| 31.5–50s | 第二幕 | 阵列斩杀、链锤对决、红色幕墙 |
| 49.5–90s | 第三幕 | 对白、终结指令、刀尖向天 |

## 命令

```bash
cd videos/blade-aim
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy

npm run check
npm run render -- --output renders/blade-aim.mp4
# 若 Cursor 播不了，补静音轨：
ffmpeg -y -i renders/blade-aim.mp4 -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
  -c:v libx264 -profile:v main -pix_fmt yuv420p -c:a aac -shortest -movflags +faststart \
  renders/blade-aim.mp4
```
