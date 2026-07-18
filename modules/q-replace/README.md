# 人物视频替换

将视频中所有真人全身替换为指定角色（Q 版或写实），保留原背景与音轨。

## 安装

```bash
npm run qreplace:setup
```

若 PyPI 下载慢，可用镜像：

```bash
cd modules/q-replace
python3 -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
python3 -m pip install onnxruntime -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

> 若 pyenv Python 缺少 `_lzma`，YOLO 会自动降级为 OpenCV HOG 人体检测。

## 运行

```bash
# Q 版全量处理（首次建议先预览）
python3 modules/q-replace/run.py /path/to/video.mp4

# Q 版快速预览（45 帧分析、跳过 SDXL 扩散）
npm run qreplace:preview -- /path/to/video.mp4

# 写实美女换人（保留背景/动作/音轨）
npm run qreplace:realistic:preview -- /path/to/video.mp4
npm run qreplace:realistic -- /path/to/video.mp4

# 从中间阶段恢复
python3 modules/q-replace/run.py /path/to/video.mp4 --from-stage synthesize
```

## 写实模式

生成角色定稿图：

```bash
npm run qreplace:character-ref
```

写实换人示例（自定义输出目录与参考视频）：

```bash
python3 modules/q-replace/run.py /path/to/video.mp4 \
  --profile realistic \
  --character-ref modules/q-replace/assets/realistic-dancer/ref_front.png \
  --output-dir modules/q-replace/work/output/ref-dance-realistic \
  --preview-only \
  --frame-limit 45
```

配置文件：[`config.realistic.yaml`](config.realistic.yaml)

## 输出

```
modules/q-replace/output/{video_stem}/
  preview_3s.mp4   # 中间 3 秒样片
  final.mp4        # 成品（保留原音轨）
```

## 阶段

1. `probe` — ffprobe + 场景切分 + 抽帧
2. `track` — YOLOv8 + BoT-SORT 多人追踪与 mask
3. `motion` — MediaPipe 姿态/表情采集
4. `identity` — 每人自动生成角色定稿（或使用 `--character-ref`）
5. `synthesize` — 关键帧生成 + 光流中间帧
6. `composite` — 回贴原背景
7. `assemble` — 编码 + 原音轨 mux

## 选项

固定角色图替换（保留动作/口型）示例：

```bash
python3 modules/q-replace/run.py modules/beat-montage/work/output/123.mp4 \
  --character-ref /path/to/character.png \
  --output-dir modules/beat-montage/work/output/123-q-work \
  --from-stage synthesize \
  --keyframe-interval 12
```

| 参数 | 说明 |
|------|------|
| `--profile` | 预设配置：`default`（Q 版）或 `realistic`（写实） |
| `--config` | 自定义 YAML 配置路径 |
| `--character-ref` | 固定角色参考图，所有人共用同一外观 |
| `--keyframe-interval` | 姿态重绘关键帧间隔（越大越快，光流补中间帧） |
| `--skip-wav2lip` | 跳过 Wav2Lip，仅用 blendshape 口型 |
| `--no-diffusion` | 跳过 SDXL，使用本地风格化降级（快速测试） |
| `--preview-only` | 只输出 3s 预览 |
| `--frame-limit N` | 限制分析帧数 |
| `--from-stage` | 从指定阶段恢复 |

## 可选 Wav2Lip

本地推理环境约定路径：

- 仓库：`~/Wav2Lip`
- 权重：`~/Wav2Lip/checkpoints/wav2lip_gan.pth`
- 人脸检测：`~/Wav2Lip/face_detection/detection/sfd/s3fd.pth`
- Python：优先使用 `~/Wav2Lip/.venv/bin/python`

一键安装（Apple Silicon / Python 3.12 可用）：

```bash
npm run qreplace:setup-wav2lip
# 或
bash modules/q-replace/scripts/setup_wav2lip.sh
```

启用：在 `config.yaml` 设置 `synthesis.wav2lip_enabled: true`（默认已开）。跳过：`--skip-wav2lip`。

冒烟测试：

```bash
# 准备一张含人脸的 png/jpg 与一段 wav 后：
~/Wav2Lip/.venv/bin/python ~/Wav2Lip/inference.py \
  --checkpoint_path ~/Wav2Lip/checkpoints/wav2lip_gan.pth \
  --face /path/to/face.png \
  --audio /path/to/audio.wav \
  --outfile /tmp/wav2lip_smoke.mp4
```
