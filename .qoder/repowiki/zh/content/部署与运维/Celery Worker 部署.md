# Celery Worker 部署

<cite>
**本文档引用的文件**
- [run_celery_worker.py](file://scripts/run_celery_worker.py)
- [celery.py](file://internal/infra/celery.py)
- [celery_task.py](file://pkg/celery_task.py)
- [tasks.py](file://internal/tasks/celery/tasks.py)
- [setting.py](file://internal/config/setting.py)
- [Dockerfile](file://Dockerfile)
</cite>

## 目录
1. [简介](#简介)
2. [部署架构与环境要求](#部署架构与环境要求)
3. [核心脚本实现分析](#核心脚本实现分析)
4. [参数配置详解](#参数配置详解)
5. [启动命令与使用示例](#启动命令与使用示例)
6. [依赖与配置共享](#依赖与配置共享)
7. [容器化部署建议](#容器化部署建议)
8. [结论](#结论)

## 简介
本文档详细说明了 FastAPI 后端项目中 Celery Worker 的独立部署流程。重点分析 `scripts/run_celery_worker.py` 脚本的实现逻辑，阐述其如何启动工作进程、处理系统兼容性、配置核心参数以及与主应用的集成方式。文档旨在为开发和运维人员提供清晰的部署指南和深入的技术理解。

## 部署架构与环境要求
本项目的 Celery Worker 采用与主应用解耦的独立部署模式。Worker 进程负责执行异步任务和定时任务，通过 Redis 作为消息代理（Broker）与主应用通信。这种架构提高了系统的可伸缩性和稳定性。

**关键环境要求**：
- **操作系统**：明确禁止在 Windows 系统上运行，仅支持 POSIX 系统（如 Linux 或 macOS）。这是由于 Celery 的 `prefork` 池（默认池）依赖于 `fork()` 系统调用，而该调用在 Windows 上不可用。
- **依赖环境**：Worker 必须与主应用（FastAPI 服务）共享完全相同的 Python 依赖环境和配置，特别是 `broker_url`（消息代理地址）和 `backend_url`（结果后端地址），以确保任务的正确分发和状态查询。

**Section sources**
- [run_celery_worker.py](file://scripts/run_celery_worker.py#L8-L10)
- [Dockerfile](file://Dockerfile)

## 核心脚本实现分析
`scripts/run_celery_worker.py` 脚本是启动 Celery Worker 的入口点，其核心逻辑清晰且健壮。

### 导入与初始化
脚本首先从 `internal.celery_tasks.__init__` 模块导入 `default_celery_client` 和 `default_queue`。`default_celery_client` 是一个封装了 Celery 应用实例的 `CeleryClient` 对象，它在 `internal/infra/celery.py` 中被创建并配置，包含了任务模块、路由规则、定时任务表等所有必要信息。

### 系统兼容性检查
脚本在 `main()` 函数的开头执行了显式的系统检查：
```python
if os.name == "nt":
    print("Error: This worker script does not support Windows. Please use a POSIX system (Linux/macOS).")
    sys.exit(1)
```
此检查至关重要，因为它能立即阻止用户在不兼容的 Windows 环境中启动 Worker，避免了因底层 `fork()` 调用失败而导致的难以诊断的运行时错误。`os.name` 为 `"nt"` 是 Windows 系统的标识。

### 启动工作进程
脚本最终通过调用 `default_celery_client.app.worker_main(argv)` 来启动 Worker。使用 `worker_main` 方法而非直接调用 `celery` 命令行工具，可以避免 Click 命令行解析器对命令名的潜在问题，确保了启动过程的稳定性和可预测性。

**Section sources**
- [run_celery_worker.py](file://scripts/run_celery_worker.py#L1-L38)
- [celery.py](file://internal/infra/celery.py#L93-L117)
- [celery_task.py](file://pkg/celery_task.py#L24-L71)

## 参数配置详解
`run_celery_worker.py` 脚本定义了一组核心参数，这些参数控制着 Worker 的行为。

### 默认参数值
脚本为以下关键参数设置了默认值：
- **queues**：默认值为 `default_queue`。该值来源于 `internal/infra/celery.py` 中 `CeleryClient` 的 `task_default_queue="default"` 配置。它指定了 Worker 监听的任务队列。
- **loglevel**：默认值为 `"debug"`。这设置了 Worker 日志的详细程度。
- **pool**：默认值为 `"prefork"`。这是 Celery 的默认工作池类型，利用多进程来并行处理任务。
- **concurrency**：默认值为 `"4"`。这定义了 Worker 启动的并发工作进程（或线程）数量。

### 参数覆盖机制
脚本通过 `sys.argv[1:]` 机制提供了极高的灵活性。用户可以在命令行中追加任意的 Celery 命令行选项，这些选项的优先级最高，会覆盖脚本中的默认值。例如，`--logfile=celery.log` 会将日志输出到指定文件，`-l info` 会将日志级别从 `debug` 降低到 `info`。

**Section sources**
- [run_celery_worker.py](file://scripts/run_celery_worker.py#L13-L21)
- [celery.py](file://internal/infra/celery.py#L101)

## 启动命令与使用示例
启动 Celery Worker 的命令非常直接。

### 基本命令
```bash
python scripts/run_celery_worker.py
```
此命令将以默认参数启动 Worker。

### 带自定义参数的命令
```bash
python scripts/run_celery_worker.py --logfile=celery.log
```
此命令在启动 Worker 的同时，通过 `extra_cli_args` 机制将日志输出重定向到 `celery.log` 文件。

### 完整的参数化命令
```bash
python scripts/run_celery_worker.py -l info --pool=prefork --concurrency=8 --logfile=worker.log
```
此命令覆盖了日志级别、并发数和日志文件等所有默认参数。

**Section sources**
- [run_celery_worker.py](file://scripts/run_celery_worker.py#L20-L21)

## 依赖与配置共享
确保 Worker 与主应用的正确协同工作，依赖和配置的共享是关键。

### Python 依赖
Worker 必须在与主应用完全相同的 Python 虚拟环境中运行。这确保了所有任务函数（如 `internal/tasks/celery/tasks.py` 中定义的）及其依赖的库都可用。项目使用 `uv` 和 `pyproject.toml` 来管理依赖，保证了环境的一致性。

### 配置同步
核心配置，特别是 `broker_url` 和 `backend_url`，必须在主应用和 Worker 之间保持一致。在本项目中，这些配置通过 `internal/config/setting.py` 从环境变量（如 `.env.prod`）加载，确保了配置的统一。`internal/infra/celery.py` 中的 `celery_client` 实例使用了 `setting.redis_url` 作为其 `broker_url` 和 `backend_url`。

**Section sources**
- [celery.py](file://internal/infra/celery.py#L95-L96)
- [setting.py](file://internal/config/setting.py)
- [Dockerfile](file://Dockerfile)

## 容器化部署建议
为了实现最佳的可维护性和可扩展性，强烈建议将 Celery Worker 部署在独立的容器或 Kubernetes Pod 中。

### 与主应用解耦
将 Worker 与 FastAPI 主应用分离部署，可以实现：
- **独立伸缩**：可以根据任务负载独立地增加或减少 Worker 实例的数量，而无需影响 API 服务。
- **资源隔离**：CPU 密集型或 I/O 密集型任务不会影响 API 的响应延迟。
- **独立更新**：可以独立部署和更新任务逻辑，而无需重启整个应用。

### Docker 部署示例
虽然 `Dockerfile` 定义了主应用的镜像，但可以基于此镜像创建一个专门用于 Worker 的镜像，或者在同一个镜像中通过不同的 `ENTRYPOINT` 或 `CMD` 来启动 Worker。例如，在 Kubernetes 的 `Deployment` 配置中，可以为 Worker 定义一个独立的 `Deployment`，其容器命令为 `python scripts/run_celery_worker.py`。

**Section sources**
- [Dockerfile](file://Dockerfile)
- [run_celery_worker.py](file://scripts/run_celery_worker.py)

## 结论
`scripts/run_celery_worker.py` 脚本提供了一个健壮、灵活且易于理解的 Celery Worker 启动方案。它通过显式的系统检查保证了兼容性，通过合理的默认值和命令行参数覆盖机制提供了配置灵活性，并通过 `worker_main` 方法确保了启动的稳定性。遵循本文档的指导，将 Worker 与主应用解耦并部署在独立的容器中，是构建高可用、可伸缩的异步任务处理系统的最佳实践。