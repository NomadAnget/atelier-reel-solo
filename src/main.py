"""atelier-reel-solo 组装入口(产品接线)—— 单一操作表单的视频翻译工具(仅本地化)。

域集 = video 依赖闭包:web / scheduler / task(+pipeline-video 插件)/ engines /
platform_adapters / publishers(契约桩)。装配原语来自 atelier_core.boot;
"装哪些域" = src/ 下的域子模块(目录即路由),domain_root=本包。

不含:daemons(监控)、media、digest、sentinel。gateway 关、task 本地、无进程域;
publishers 仅契约桩(fill_noop 空转)满足 scheduler/web 的发布契约闭环,不实际发布。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from atelier_core.boot.assembly import (
    Handlers,
    _acquire_single_instance_lock,
    _housekeeping_loop,
    build_hub,
    build_store,
    self_test,
)
from atelier_core.boot.composition import BuildContext
from atelier_core.core import config, logger

DOMAIN_ROOT = __package__          # = "src";内核据此发现本变体的域

_SHUTDOWN_DEADLINE = 20.0


async def serve(config_path: str | None = None) -> None:
    cfg = config.load(config_path)
    logger.set_level(cfg.logger.level)
    logger.info("基建配置来源:%s", cfg.source, layer="CORE", component="Main")

    lock_fd = _acquire_single_instance_lock(cfg.paths.store_db)
    if lock_fd is None:
        logger.error("已有 hub 独占数据目录 %s,拒绝启动", cfg.paths.store_db,
                     layer="CORE", component="Main")
        return

    import os
    os.environ.setdefault("GCP_MODELS_DIR", cfg.paths.models_dir)

    svc: dict = {}
    # ── 域 handler 接线(publishers=远程契约桩,不接本地,交 fill_noop 空转)──────────
    scheduler_handlers: Handlers = {
        "on_job_requested":      lambda e: svc["scheduler"].on_job_requested(e),
        "on_job_cancel":         lambda e: svc["scheduler"].on_job_cancel(e),
        "on_job_delete":         lambda e: svc["scheduler"].on_job_delete(e),
        "on_job_republish":      lambda e: svc["scheduler"].on_job_republish(e),
        "on_publish_discard":    lambda e: svc["scheduler"].on_publish_discard(e),
        "on_schedule_due":       lambda e: svc["scheduler"].on_schedule_due(e),
        "on_monitor_discovered": lambda e: svc["scheduler"].on_monitor_discovered(e),
        "on_job_finished":       lambda e: svc["scheduler"].on_job_finished(e),
        "on_job_progress":       lambda e: svc["scheduler"].on_job_progress(e),
        "on_publish_finished":   lambda e: svc["scheduler"].on_publish_finished(e),
        "on_channel_targets_edit": lambda e: svc["scheduler"].on_channel_targets_edit(e),
    }
    # task 槽位 = 聚合后 header 的 SUBSCRIBES(基础 + pipeline-video 的 on_kb_*);
    # 惰性索引 _task_rt:挂载期以 lambda 占位,build 后填真 handler(消息触发时解析)。
    from .task import header as _task_header
    _task_rt: dict = {}
    task_handlers: Handlers = {
        slot: (lambda s: lambda e: _task_rt["h"][s](e))(slot)
        for slot in set(_task_header.SUBSCRIBES.values())
    }
    engines_handlers: Handlers = {
        "on_settings_edit": lambda e: svc["engines_settings_edit"](e),
    }
    platform_adapters_handlers: Handlers = {
        # 注:on_accounts_snapshot(engine_ 账号镜像)已随 publishers 去镜像删除。
        "on_settings_edit":     lambda e: svc["ingest"].on_settings_edit(e),
    }
    remote_handlers: dict[str, Handlers] = {
        "scheduler": scheduler_handlers,
        "task": task_handlers,
        "engines": engines_handlers,
        "platform_adapters": platform_adapters_handlers,
    }

    bus, windows = await build_hub(
        remote_handlers, fill_noop=True, journal_db=cfg.paths.journal_db,
        queue_size=cfg.bus.queue_size, max_attempts=cfg.bus.max_attempts,
        put_timeout=cfg.bus.put_timeout, domain_root=DOMAIN_ROOT)
    store, store_windows = await build_store(cfg.paths.store_db, domain_root=DOMAIN_ROOT)

    from atelier_core.core.log_store import LogStoreHandler
    log_sink = LogStoreHandler(cfg.paths.store_db, batch=cfg.logstore.batch,
                               flush_interval=cfg.logstore.flush_interval,
                               queue_max=cfg.logstore.queue_max)
    logging.getLogger(logger.ROOT).addHandler(log_sink)

    # ── engines 设置底座 ─────────────────────────────────────────────────────────
    from atelier_core.core.settings import SettingsStore, edit_handler
    from .engines.schema import EngineSettings
    engines_settings = SettingsStore(store, store_windows["engines"],
                                     "engines_settings", EngineSettings, layer="ENGINES")
    svc["engines_settings_edit"] = edit_handler(engines_settings, "engines")
    await engines_settings.get()

    # ── task 域:build 聚合(基础服务 + pipeline-video 插件注册 + 门面 init)──────────
    from .task import build as task_build
    ctx = BuildContext(hub=store, stores=store_windows, publish=windows["task"],
                       loop=asyncio.get_running_loop(), cfg=cfg, bus=bus)
    _task_rt["h"] = task_build.build(ctx).handlers   # 填真 handler(占位 lambda 据此解析)

    # ── scheduler ────────────────────────────────────────────────────────────────
    from .scheduler.impl.publish_service import PublishService
    from .scheduler.impl.service import JobSchedulerService
    svc["scheduler"] = JobSchedulerService(
        windows["scheduler"], store, store_windows["scheduler"],
        publish_service=PublishService(windows["scheduler"], store),
        task_process=None)          # task 本地,无进程域控制器

    # ── platform_adapters(YouTube 采集;仅本地化不发布,但下载需采集门面)──────────────
    from .platform_adapters.impl.service import ConnectionService
    svc["connections"] = ConnectionService(
        windows["platform_adapters"], store, store_windows["platform_adapters"])
    from .platform_adapters import ingest as pa_ingest
    from .platform_adapters import youtube_token
    svc["ingest"] = pa_ingest.init(store, store_windows["platform_adapters"])
    youtube_token.init(store, store_windows["platform_adapters"])

    scheduler_worker = asyncio.create_task(svc["scheduler"].run_worker(), name="scheduler_worker")
    housekeeping_task = asyncio.create_task(
        _housekeeping_loop(bus, store, cfg.retention), name="housekeeping")

    # ── web(单端口 + in-repo 单表单前端)──────────────────────────────────────────
    web_server = web_task = None
    if cfg.web.enabled and "web" in windows:
        import uvicorn

        from .web.impl.service import build_web_app
        web_app = build_web_app(bus, store, windows["web"], dist_dir=cfg.web.dist_dir or None)
        web_server = uvicorn.Server(uvicorn.Config(
            web_app, host=cfg.web.host, port=cfg.web.port, log_config=None, access_log=False))
        web_task = asyncio.create_task(web_server.serve(), name="web")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    logger.info("atelier-reel-solo 运行中(%d 域,port=%d)。Ctrl-C 停机",
                len(windows), cfg.web.port, layer="CORE", component="Main")
    await stop.wait()

    logger.info("停机中…", layer="CORE", component="Main")
    if web_server is not None:
        web_app.state.close_streams()
        web_server.should_exit = True
        await asyncio.gather(web_task, return_exceptions=True)
    for t in (scheduler_worker, housekeeping_task):
        t.cancel()
    await asyncio.gather(scheduler_worker, housekeeping_task, return_exceptions=True)
    await store.close()
    await bus.close()
    if bus.journal is not None:
        await bus.journal.close()
    log_sink.flush(timeout=3.0)
    logging.getLogger(logger.ROOT).removeHandler(log_sink)
    log_sink.shutdown()
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="atelier-reel-solo 组装入口")
    parser.add_argument("--check", action="store_true", help="声明自检后退出")
    parser.add_argument("--config", default=None, help="基建配置路径(默认 ./config.toml)")
    args = parser.parse_args()
    asyncio.run(self_test(DOMAIN_ROOT) if args.check else serve(args.config))
