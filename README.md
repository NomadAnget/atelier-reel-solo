# atelier-reel-solo

**Atelier 变体:单一操作表单的视频翻译工具(仅本地化)。**

提交一个视频(YouTube URL / 本地路径)+ 目标语言 → 跑视频翻译管线 → 取本地化成片。
无频道监控、无发布出闸、无日报——就一个操作表单。

## 组成(video 依赖闭包)
- **内核**:`atelier-core`(uv 依赖,绝对导入 `atelier_core.*`)
- **域子模块**(挂 `src/<域>`):web · scheduler · task · engines · platform_adapters · publishers(契约桩)
- **管线子模块**:`src/pipelines/video`(atelier-pipeline-video)
- **前端**:in-repo 单表单(`src/web/frontend`,只经命令/查询/SSE/快照四形状)

不含:daemons(监控)、media、pipeline-digest、sentinel。publishers 仅契约桩(gateway 关、fill_noop 空转)满足 scheduler/web 的发布契约闭环;不实际发布。

## 跑
```bash
uv sync                 # 装 atelier-core + 引擎栈(见 pyproject 注释)
git submodule update --init --recursive
cd src/web/frontend && npm ci && npm run build && cd -
uv run python -m src.main
```
