# atelier-reel-solo

**Atelier 变体:单一操作表单的视频翻译工具(仅本地化)。**

提交一个视频(YouTube URL / 本地路径)+ 目标语言 → 跑视频翻译管线 → 取本地化成片。
无频道监控、无发布出闸、无日报——就一个操作表单。

## 组成(video 依赖闭包)
- **内核**:`atelier-core`(uv 依赖,绝对导入 `atelier_core.*`)
- **域子模块**(挂 `src/<域>`):web · scheduler · task · engines · platform_adapters · publishers(契约桩)
- **管线子模块**:`src/pipelines/video`(atelier-pipeline-video)
- **前端**:in-repo 单表单(`src/web/frontend`,只经命令/查询/SSE/快照四形状)

不含:media、pipeline-digest、sentinel。**daemons 作契约桩挂载**(fill_noop 空转、不起监控循环)——因 web/scheduler/platform_adapters 声明了一批只被 daemons 订阅的持久 topic(monitor/*、digest/*、job/status_changed、auth/expired),不挂它会悬空致组装拒挂;桩满足闭环,功能上仍无监控(循环不启)。publishers 仅契约桩(gateway 关、fill_noop 空转)满足 scheduler/web 的发布契约闭环;不实际发布。

## 跑(复用现有引擎栈,别用 `uv run`)

引擎栈(torch/faster-whisper/… CUDA 锁死那 100+ 依赖)在 `/home/Architecture/.venv`,不重建;
把 atelier-core 装进这个胖 venv,直接用它跑:

```bash
git submodule update --init --recursive      # 拉域/管线子模块(含 engines 的 indextts)
uv pip install --python /home/Architecture/.venv/bin/python --no-deps \
    "atelier-core @ git+http://debian.lan:3257/Carnation/atelier-core.git"
/home/Architecture/.venv/bin/python -m src.main --config config.toml
```

- 前端是 **in-repo 静态页**(`frontend/dist/index.html`),web 直接伺服,**无需 npm 构建**。
- **不要 `uv run`**:它会建隔离 venv、只装 atelier-core、**没有引擎栈**,跑到 engines 即缺 torch。
- 独立部署(带全套引擎栈的干净环境)时,把旧 Architecture pyproject 的重型依赖段并入本 pyproject 再 `uv sync`;当前是"借胖 venv"的开发跑法。

