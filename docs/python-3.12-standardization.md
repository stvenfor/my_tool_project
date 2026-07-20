# my_tool_project：Python 3.12 统一环境与迁移指南

> 状态：迁移设计与验证基线，不代表全仓迁移已经完成
> 基线日期：2026-07-20
> 目标版本：CPython 3.12.13，后续仅在完整回归通过后升级 3.12 补丁版本

## 1. 结论

`my_tool_project` 可以统一使用 Python 3.12，但“统一”应指统一解释器大版本和执行规范，而不是让所有模块共用一个全局 `site-packages`。本仓库同时包含标准库工具、数据与图片处理、音频处理、Whisper、PyTorch、MediaPipe、ONNX Runtime、Diffusers 和视频流水线；这些依赖的二进制轮子、NumPy 约束和硬件后端并不完全一致。正确目标是：

1. 仓库统一固定 CPython 3.12.13。
2. 每个有独立依赖边界的模块使用自己的虚拟环境和锁文件。
3. npm、定时任务和人工命令都调用模块虚拟环境中的解释器。
4. ETF Monitor 作为第一条已验证基准；其余模块按风险从低到高迁移。
5. 不原地升级旧虚拟环境；任何失败都通过删除并重建虚拟环境回滚。

ETF Monitor 已经在 Python 3.12.13 下通过全部 142 项测试，可以立即作为统一工作的参考实现。整个仓库的 Python 源码能够通过 3.12 语法编译，但这不等于所有第三方依赖、外部服务、模型权重和端到端视频流水线已经完成兼容性验证。

## 2. 适用范围

本文覆盖 Git 当前跟踪的 Python 业务模块、根 npm workspace 对这些模块的调用方式，以及 Codex 本地自动化任务。Node.js、Remotion、Playwright、ffmpeg、模型文件、浏览器登录态和云服务凭据不属于 Python 版本管理本身，但必须进入各模块的端到端验收。

本文不把被 `.gitignore` 排除的实验目录或本地克隆代码视为仓库基线。例如本机存在的 `modules/openmontage/` 和 `videos/` 内容可以单独迁移，但不能用它们的本地状态证明 Git 仓库已经完成统一。

## 3. 当前状态审计

### 3.1 已确认事实

| 检查项 | 当前结果 | 含义 |
|---|---:|---|
| 主检出目录中的 `python3` | Python 3.12.13，来自 pyenv | 主目录交互式工具会话已经使用目标版本 |
| 隔离 worktree 中的 `python3` | 曾解析为系统 Python 3.9.6 | `PATH` 把 `/usr/bin` 放在 pyenv shim 前，证明不能依赖命令名推断版本 |
| Git 跟踪的 Python 文件 | 146 个 | 统计不包含 `.venv`、缓存和被忽略目录 |
| Python 3.12 语法检查 | 通过 | 只能证明源码可被 3.12 编译 |
| ETF Monitor 测试 | 142/142 通过 | 已验证标准库实现、CLI、扫描与组合规则 |
| 根 `.python-version` | 缺失 | 新终端和自动任务仍可能解析到其他解释器 |
| 根 `pyproject.toml` / 统一锁文件 | 缺失 | 没有机器可读的 Python 版本和依赖治理合同 |
| 通用 `.venv` 忽略规则 | 缺失 | 创建模块虚拟环境前必须先补充 `.gitignore` |
| npm 中的 Python 命令 | 普遍使用 `python3` | 实际版本取决于任务运行时的 `PATH` |
| CI 中的 Python 3.12 门禁 | 缺失 | 目前没有持续验证版本漂移 |

用于建立基线的核心命令如下：

```bash
python312_bin="$(pyenv root)/versions/3.12.13/bin/python3"
"$python312_bin" --version
git ls-files '*.py' | wc -l
"$python312_bin" -m compileall -q modules
cd modules/etf-monitor
"$python312_bin" -m unittest discover -s tests -p 'test_*.py'
```

### 3.2 当前全局环境不能直接复用

当前 Python 3.12 全局环境的 `python3 -m pip check` 已报告依赖不一致：

- `opencv-python` 与 `opencv-contrib-python` 要求 NumPy 2.x，而当前为 NumPy 1.26.4。
- `tifffile` 要求 NumPy 2.1 或更高。
- 当前 `rembg` 要求 NumPy 2.3 或更高。

这不是 Python 3.12 本身不兼容，而是多个模块在同一个环境里使用宽泛版本范围造成了解析漂移。继续向同一环境安装包，可能出现“安装成功、运行失败”，也可能为了修复一个模块而破坏另一个模块。因此不得把当前全局环境作为生产或自动化运行环境。

### 3.3 已解决的 Python 3.12 测试命名冲突

Python 3.12 环境中曾存在第三方顶层包 `tests`，它抢先于 ETF Monitor 的本地 `tests/` 被导入。仓库已通过增加 `modules/etf-monitor/tests/__init__.py` 把本地测试目录变为明确的常规包，消除了命名遮蔽。这个修复没有生产运行时副作用，也是 ETF 142 项测试能够稳定通过的组成部分。

## 4. 目标环境架构

### 4.1 三层约束

**仓库层：固定解释器。** 根目录使用 `.python-version` 固定 `3.12.13`，并在机器可读配置中声明 `requires-python = ">=3.12,<3.13"`。补丁版本升级必须经过同样的测试门禁。

**模块层：隔离依赖。** 有第三方依赖的模块在自身目录维护 `.venv` 和锁文件。实施前先在根 `.gitignore` 增加通用 `.venv` 规则；虚拟环境永不提交 Git，锁文件必须提交。标准库模块也可以建立轻量 `.venv`，以保证自动化不依赖系统 Python。

**执行层：显式选择解释器。** 人工命令、npm script、LaunchAgent 和 Codex 自动化不得假设 `python3` 一定指向 3.12。它们应调用模块 `.venv/bin/python`，或经过一个会检查版本的启动脚本。

推荐形态：

```text
my_tool_project/
├── .python-version                # 3.12.13
├── pyproject.toml                 # 仓库级工具和 requires-python
├── modules/
│   ├── etf-monitor/
│   │   ├── .venv/                 # 本地生成，Git 忽略
│   │   ├── pyproject.toml         # 模块依赖合同
│   │   └── uv.lock                # 或等价的可复现锁文件
│   └── q-replace/
│       ├── .venv/
│       ├── pyproject.toml
│       └── uv.lock
└── scripts/
    └── python-module              # 统一版本检查与模块解释器路由
```

这里的 `uv.lock` 是推荐方案，不是唯一方案。如果团队继续使用 pip，也应生成按模块维护、带确定版本的 lock 文件；仅保留 `package>=x` 的宽泛 `requirements.txt` 不足以复现环境。

### 4.2 为什么不共享一个根 `.venv`

根 `.venv` 适合只安装 lint、测试和文档工具，不适合承载所有业务依赖。语音、图像生成与角色替换模块对 NumPy、Torch、torchaudio、torchcodec、OpenCV、MediaPipe、ONNX Runtime 和模型框架的版本要求会独立变化。隔离后可以：

- 单独升级某个模型栈，不影响 ETF 或日报工具。
- 保持 PyTorch 与 torchaudio 的配套版本。
- 为 Apple Silicon/MPS、CPU 或其他运行目标选择不同轮子。
- 删除并重建单个模块，而不用修复整个全局环境。

## 5. 模块风险分层

下面的风险表示迁移验证工作量，不表示模块质量。Git 当前跟踪 14 个含 Python 源码的模块，其中 8 个提交了 `requirements.txt`。

| 模块 | Python 文件 | 依赖清单 | 风险 | 主要依据与最低验收 |
|---|---:|:---:|:---:|---|
| `etf-monitor` | 12 | 无 | 低 | 仅标准库；已在 3.12.13 下通过 142 项测试，继续验证 CLI JSON 与定时 fixture |
| `shared` | 2 | 无 | 低 | 仅标准库 Python import；另需验证 ffmpeg/ffprobe 边界 |
| `dance-remake` | 4 | 无 | 低 | 仅标准库 Python import；跑一次节拍/合成短样例 |
| `hot-topic-infographic` | 18 | 有 | 低 | Pillow、jsonschema 依赖面小；跑布局、校验和导出 smoke |
| `beat-montage` | 14 | 有 | 中 | NumPy、librosa、SoundFile、Pillow 与 ffmpeg/yt-dlp；Pillow 当前未在清单声明 |
| `cat-drama-video` | 5 | 无 | 中 | 使用 edge-tts、Pillow 与 ffmpeg，但缺少独立 Python 依赖清单 |
| `cffex-daily` | 3 | 无 | 中 | 使用 Pillow、Python Playwright/Chromium，但缺少依赖清单和浏览器安装合同 |
| `city-bilingual-video` | 11 | 有 | 中 | edge-tts、Pillow、NumPy、Whisper/Torch；跑转写、TTS、storyboard 与短片链路 |
| `cognitive-video` | 10 | 有 | 中 | edge-tts、Pillow、NumPy、Whisper/Torch；依赖只有宽松下限 |
| `three-kingdoms-english-video` | 11 | 有 | 中 | edge-tts、Pillow、NumPy、Whisper/Torch；需模型加载和代表性渲染 |
| `city-healing-video` | 8 | 有 | 高 | Torch、torchaudio、torchcodec、Lhotse、Sopro、ZipVoice；外部克隆和模型栈需固定 |
| `q-replace` | 17 | 有 | 高 | NumPy/OpenCV、MediaPipe、Ultralytics、rembg、Torch、Diffusers、ONNX 与 Wav2Lip |
| `video-factory` | 17 | 无 | 高 | 没有自身清单，却通过同一解释器聚合多个模块和可选 ZipVoice 依赖 |
| `viral-english-dub` | 14 | 有 | 高 | Whisper、Torch、ModelScope、Demucs、CosyVoice；外部克隆和版本组合复杂 |

对没有独立 `requirements.txt` 的模块，不能据此认定“无依赖”；需要结合导入语句、调用的兄弟 CLI、Node 工具和系统命令生成模块清单。`video-factory` 可以通过 CLI 编排兄弟模块，但不应把兄弟模块的 Python 包全部安装进自己的环境。

## 6. 依赖锁定策略

### 6.1 推荐规则

1. 每个模块声明 `requires-python = ">=3.12,<3.13"`。
2. 直接依赖写入模块 `pyproject.toml`，传递依赖由锁文件确定。
3. PyTorch、torchaudio、torchvision 等成组依赖必须一起升级和验证。
4. NumPy、OpenCV、MediaPipe、rembg、tifffile 作为重点兼容组，不允许只升级其中一个。
5. 模型运行时与开发工具分组，避免生产环境安装无关工具。
6. 所有安装都使用 `python -m pip` 或锁文件工具，禁止裸 `pip`。
7. 安装完成必须运行 `python -m pip check`；非零退出即视为环境不可交付。

### 6.2 不应采用的做法

- 不在系统 Python 或 pyenv 的全局 site-packages 中继续叠加业务包。
- 不通过“反复安装不同 NumPy 版本直到能跑”解决冲突。
- 不在旧 `.venv` 上原地更换 Python 小版本。
- 不把 `.venv`、模型缓存、访问令牌或本机绝对路径提交 Git。
- 不把一次 import 成功当作端到端兼容证明。

## 7. 分阶段迁移计划

### 阶段 0：保存基线

在独立分支完成环境治理；记录目标提交、macOS/CPU 架构、Python 版本和各模块代表性命令。迁移前保留当前锁文件或导出清单，但不要把已有冲突的全局 `pip freeze` 直接当成新锁文件。

### 阶段 1：固定仓库版本

```bash
pyenv install -s 3.12.13
pyenv local 3.12.13
python --version
```

提交 `.python-version` 和仓库级 Python 合同。增加一个快速检查，要求 `sys.version_info[:2] == (3, 12)`；自动任务在检查失败时应明确退出，而不是继续用错误版本运行。

### 阶段 2：把 ETF Monitor 建成参考模块

```bash
cd modules/etf-monitor
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

ETF Monitor 没有第三方运行依赖，因此它适合先验证解释器固定、npm 路由、测试发现和 Codex 自动化。验收时还应执行 `audit` 与 fixture-backed `scheduled-check`，确认输出仍为唯一、严格的 JSON 文档，并保持 `orders_placed=false`。

### 阶段 3：迁移轻量模块

按 `cffex-daily`、`hot-topic-infographic`、`cat-drama-video`、`video-factory`、`shared`、`beat-montage`、`dance-remake` 的顺序推进。每个模块先创建干净 3.12 环境，再安装锁定依赖，最后执行最短可代表真实工作的 smoke test。

### 阶段 4：迁移 AI/模型模块

Whisper、Torch、MediaPipe、ONNX 和 Diffusers 模块逐个迁移，不并行共用环境。每个模块至少验证：

1. 核心包导入和版本输出。
2. 模型能在目标设备加载。
3. 一个小输入能完成推理。
4. 代表性流水线能产生可读产物。
5. `python -m pip check` 无冲突。

对 Apple Silicon，CPU/MPS 回退必须显式记录。外部模型仓库需要自己的 Python 3.12 兼容补丁时，应在该仓库或安装脚本中管理，不要用运行时修改全局包的方式隐藏问题。

### 阶段 5：收口入口和自动化

更新根 npm scripts，使其进入正确模块环境。推荐把解释器选择集中到一个启动器，而不是在几十条 npm 命令中硬编码本机路径。启动器至少检查：模块名合法、解释器存在、Python 为 3.12、命令退出码原样返回。

迁移完成前，旧 `python3` 命令可以保留，但必须在 CI 和自动化入口前执行版本检查。迁移完成后，所有无人值守任务应直接调用模块虚拟环境解释器。

## 8. Codex 与定时任务

Codex 本地自动化和 LaunchAgent 往往运行在非交互 shell；它们不一定加载用户的 shell 初始化文件，因此不能仅凭交互终端里的 `python3 --version` 判断定时任务也会使用同一版本。本次文档验证已经复现了这个差异：同一台机器的主检出目录解析到 pyenv Python 3.12.13，而隔离 worktree 因 `PATH` 顺序解析到 `/usr/bin/python3` 3.9.6；显式调用 pyenv 的 3.12.13 解释器后验证恢复正常。

ETF 的两个提醒任务应通过仓库内稳定入口调用 `modules/etf-monitor/.venv/bin/python`。运行前记录解释器路径和 Python 大版本，但不得把访问令牌、账户信息或 provider 原始敏感数据写入日志。环境或行情数据异常时继续遵守原有 fail-closed 规则：只报告 `DATA_ERROR`/“无行动”，绝不连接券商或自动下单。

自动任务部署后的最小验收：

```bash
modules/etf-monitor/.venv/bin/python --version
npm run etf:test
npm run etf:audit
npm run etf:scheduled-check -- --fixture modules/etf-monitor/state/provider.json
```

## 9. CI 与质量门禁

建议把门禁分成三层：

### 9.1 仓库快速门禁

- 使用明确的 Python 3.12 runner。
- 校验 `.python-version` 与配置声明一致。
- 编译 Git 跟踪的 Python 源码。
- 检查没有提交 `.venv`、`__pycache__`、模型缓存或密钥。

### 9.2 模块门禁

- 从锁文件创建全新环境。
- 运行 `python -m pip check`。
- 执行单元测试、CLI 合同测试或 smoke test。
- 保存失败日志中的包版本和平台信息，但过滤凭据。

### 9.3 代表性端到端门禁

AI/视频模块不宜在每次小提交中下载全部模型。可以按模块维护小 fixture，普通提交运行短 smoke；定时或发布前任务运行完整代表性样例。产物验收应包含文件存在、时长/分辨率、音轨、JSON schema，以及必要的人工视觉或听觉复核。

## 10. 验收标准

只有满足以下条件，才可宣布“仓库已统一到 Python 3.12”：

- 根目录固定 Python 3.12，干净终端进入仓库后版本一致。
- 所有 Git 跟踪模块均有明确依赖边界和可复现安装方式。
- 每个模块的 `pip check` 无冲突。
- 146 个 Git 跟踪 Python 文件通过 3.12 编译检查。
- ETF Monitor 继续保持 142/142 测试通过。
- 轻量模块完成至少一个真实 CLI smoke。
- AI/模型模块完成包导入、模型加载、最小推理和代表性端到端样例。
- npm、Codex 自动化和 LaunchAgent 不再依赖不确定的系统 `python3`。
- 仓库没有纳入虚拟环境、缓存、令牌或本机绝对路径。

在这些条件全部完成前，准确说法应是“仓库目标版本为 Python 3.12，ETF Monitor 已验证，其余模块迁移中”。

## 11. 故障排查

### `python --version` 仍不是 3.12

确认 pyenv shim 位于 `PATH` 前部，并在仓库根目录检查 `pyenv version`。对无人值守任务不要依赖 shell 初始化，改为调用模块 `.venv/bin/python`。

### 测试导入了错误的 `tests` 包

确保本地测试目录包含 `__init__.py`，并从模块约定目录运行测试。不要通过删除第三方包或修改全局 `PYTHONPATH` 掩盖命名冲突。

### NumPy、OpenCV 或 rembg 冲突

删除该模块的 `.venv`，修正模块约束并重新解析锁文件；不要在共享环境里降级/升级 NumPy。重新安装后必须运行 `pip check` 和模块 smoke。

### Torch、torchaudio 或模型加载失败

检查 Python、平台、架构和成组包版本是否匹配，再检查模型所需的系统库。Apple Silicon 上同时记录 MPS 可用性与 CPU 回退结果。

### 本地可运行、定时任务失败

比较交互终端和任务日志中的解释器绝对路径、工作目录、`PATH` 和必要环境变量。优先修正启动器，不要把用户 shell 的全部环境复制进定时任务。

## 12. 回滚方案

Python 环境回滚以“重建”而不是“修补”为原则：

1. 停止受影响模块的无人值守任务。
2. 保留失败日志和锁文件差异，不保留损坏的 `.venv`。
3. 回退仓库中的版本声明、锁文件和入口脚本到上一个已验证提交。
4. 删除受影响模块 `.venv`，用回退后的合同重新创建。
5. 重新执行该模块测试或代表性 smoke 后再恢复任务。

如果只有单个 AI 模块阻塞，不应回退 ETF 或其他已经通过 3.12 验证的模块。模块隔离的价值正是在这里：允许局部暂停和局部回滚。

## 13. 维护规范

- Python 3.12 补丁升级采用独立提交，并运行全仓快速门禁与受影响模块测试。
- 依赖升级按模块进行；NumPy/模型运行时等关键组一次只处理一个模块。
- 每次依赖升级提交锁文件，并在变更说明中记录验证命令。
- 每月至少执行一次锁文件重建检查和代表性 smoke；自动化长期未运行也要视为风险。
- 新模块必须在加入根 npm workspace 前声明 Python 版本、依赖边界、环境创建命令和最小验收命令。
- 文档中的“已验证”结论必须附带日期、解释器版本和可复现命令。

## 14. 建议实施顺序

建议按以下顺序落地，不跨阶段宣布完成：

1. 提交根 `.python-version`、Python 合同与统一启动器。
2. 将 ETF Monitor 改为使用专用 3.12 `.venv`，复跑 142 项测试和定时 fixture。
3. 迁移低风险及轻量模块。
4. 为依赖较重模块生成独立锁文件，先解决 NumPy/OpenCV/rembg 组合。
5. 逐个迁移 Whisper、Torch、MediaPipe、ONNX 与 Diffusers 模块。
6. 增加 CI、定时任务 preflight 和版本漂移告警。
7. 全部验收完成后，更新本文状态为“已实施”，并记录最终锁文件和测试结果。

这条路线能统一工程约束，同时把高风险依赖问题限制在各自模块内；它比共享一个全局 Python 环境更稳定，也比把整个仓库一次性容器化更适合当前本地视频与 Apple Silicon 工作流。
