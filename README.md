# atelier-reel-solo

**Atelier 变体:单一操作表单的视频翻译工具(仅本地化)。**

> **宪法在内核仓**:体系的架构/契约/纪律以 [atelier-core/docs/](http://debian.lan:3257/Carnation/atelier-core/src/branch/master/docs)(CONSTITUTION + architecture/bus/storage/domains/boot/logging)为准。本 README 只给本变体的组装与运行导引。


提交一个视频(YouTube URL / 本地路径)+ 目标语言 → 跑视频翻译管线 → 取本地化成片。
无频道监控、无发布出闸、无日报——就一个操作表单。

## 组成(video 依赖闭包)
- **内核**:`atelier-core`(uv 依赖,绝对导入 `atelier_core.*`)
- **域子模块**(挂 `src/<域>`):web · scheduler · task · engines · platform_adapters · publishers(契约桩)
- **管线子模块**:`src/pipelines/video`(atelier-pipeline-video)
- **前端**:in-repo 单表单(`src/web/frontend`,只经命令/查询/SSE/快照四形状)

不含:media、pipeline-digest、sentinel。**daemons 作契约桩挂载**(fill_noop 空转、不起监控循环)——因 web/scheduler/platform_adapters 声明了一批只被 daemons 订阅的持久 topic(monitor/*、digest/*、job/status_changed、auth/expired),不挂它会悬空致组装拒挂;桩满足闭环,功能上仍无监控(循环不启)。publishers 仅契约桩(gateway 关、fill_noop 空转)满足 scheduler/web 的发布契约闭环;不实际发布。

## 依赖

pyproject 已**对齐**本变体所含域/管线(engines + pipeline-video 闭包)的完整运行时依赖 ——
GPU 推理栈(torch/whisperx/demucs/pyannote/paddleocr/indextts/clearvoice/…,CUDA 锁死)+ 内核
`atelier-core`(git 依赖)。`[tool.uv]` 的 index/override 与 Architecture 一致。

## 跑

**A. 干净 CUDA 机(自包含)**:
```bash
git submodule update --init --recursive
uv sync                              # 装内核 + 全套引擎栈(首次重,~数十分钟)
uv run python -m src.main --config config.toml
```

**B. 本机开发(复用旧 Architecture 已装的胖 venv,省去重装 CUDA 栈)**:
```bash
git submodule update --init --recursive
uv pip install --python /home/Architecture/.venv/bin/python --no-deps \
    "atelier-core @ git+http://debian.lan:3257/Carnation/atelier-core.git"
/home/Architecture/.venv/bin/python -m src.main --config config.toml
```

- 前端是 **in-repo 静态页**(`frontend/dist/index.html`),web 直接伺服,**无需 npm 构建**。
- 首次锁定复现:在 CUDA 机 `uv lock` 生成 `uv.lock`(当前 gitignore,未提交)。

