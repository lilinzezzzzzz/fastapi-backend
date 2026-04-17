import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest
from loguru import logger as loguru_logger

from pkg.logger import LogFormat, LoggerHandler
from pkg.logger.span import get_current_span, span_context, with_span


@with_span(span_type="service")
async def decorated_default_name() -> str | None:
    current = get_current_span()
    loguru_logger.info("decorated.default")
    return None if current is None else current.span_name


@with_span(span_type="db", name="custom.db.query")
async def decorated_custom_name() -> str | None:
    current = get_current_span()
    loguru_logger.info("decorated.custom")
    return None if current is None else current.span_name


def _configure_logger(
    tmp_path: Path,
    *,
    log_format: LogFormat,
    enqueue: bool,
) -> tuple[LoggerHandler, Path]:
    base_log_dir = tmp_path / "logs"
    manager = LoggerHandler(
        base_log_dir=base_log_dir,
        log_format=log_format,
        enqueue=enqueue,
    )
    manager.setup(write_to_console=False)
    return manager, base_log_dir


def _default_log_file(base_log_dir: Path) -> Path:
    files = list(base_log_dir.glob("*.log"))
    assert len(files) == 1
    return files[0]


def _read_json_records(file_path: Path) -> list[dict]:
    records: list[dict] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _find_record(records: list[dict], message: str) -> dict:
    for record in records:
        if record.get("message") == message:
            return record
    raise AssertionError(f"record not found for message={message}")


@pytest.fixture(autouse=True)
def cleanup_loguru():
    yield
    loguru_logger.remove()


@pytest.mark.asyncio
async def test_async_with_span_injects_fields_and_restores_context(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.JSON, enqueue=False)

    async with span_context("outer", span_type="service") as current_span:
        assert current_span.span_seq == 1
        assert current_span.span_name == "outer"
        assert current_span.span_type == "service"
        assert current_span.span_depth == 0
        assert current_span.span_path == "1:outer"
        assert get_current_span() == current_span
        loguru_logger.info("inside.outer")

    assert get_current_span() is None

    loguru_logger.complete()
    records = _read_json_records(_default_log_file(base_log_dir))

    inside_record = _find_record(records, "inside.outer")
    assert inside_record["trace_id"] == "test-trace-id"
    assert inside_record["span_seq"] == 1
    assert inside_record["span_name"] == "outer"
    assert inside_record["span_type"] == "service"
    assert inside_record["span_depth"] == 0
    assert inside_record["span_path"] == "1:outer"

    start_record = _find_record(records, "span.start")
    assert start_record["span_seq"] == 1

    end_record = _find_record(records, "span.end")
    assert end_record["span_seq"] == 1
    assert isinstance(end_record["json_content"]["elapsed_ms"], float)
    assert end_record["json_content"]["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_instrument_span_supports_default_and_custom_names(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.JSON, enqueue=False)

    async with span_context("outer", span_type="request") as outer_span:
        default_name = await decorated_default_name()
        custom_name = await decorated_custom_name()

    assert default_name == decorated_default_name.__qualname__
    assert custom_name == "custom.db.query"
    assert outer_span.span_path == "1:outer"

    loguru_logger.complete()
    records = _read_json_records(_default_log_file(base_log_dir))

    default_record = _find_record(records, "decorated.default")
    assert default_record["span_name"] == decorated_default_name.__qualname__
    assert default_record["span_type"] == "service"
    assert default_record["span_depth"] == 1
    assert default_record["span_path"] == f"{outer_span.span_path}/2:{decorated_default_name.__qualname__}"

    custom_record = _find_record(records, "decorated.custom")
    assert custom_record["span_name"] == "custom.db.query"
    assert custom_record["span_type"] == "db"
    assert custom_record["span_depth"] == 1
    assert custom_record["span_path"] == f"{outer_span.span_path}/3:custom.db.query"


@pytest.mark.asyncio
async def test_nested_error_logs_and_restores_parent_span(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.JSON, enqueue=False)

    async with span_context("outer", span_type="service") as outer_span:
        with pytest.raises(RuntimeError, match="boom"):
            async with span_context("inner", span_type="db"):
                loguru_logger.info("before.error")
                raise RuntimeError("boom")
        assert get_current_span() == outer_span
        loguru_logger.info("after.inner.error")

    assert get_current_span() is None

    loguru_logger.complete()
    records = _read_json_records(_default_log_file(base_log_dir))

    error_record = _find_record(records, "span.error")
    assert error_record["span_name"] == "inner"
    assert error_record["span_type"] == "db"
    assert error_record["span_depth"] == 1
    assert error_record["span_path"] == "1:outer/2:inner"
    assert error_record["json_content"]["error_type"] == "RuntimeError"
    assert error_record["json_content"]["elapsed_ms"] >= 0

    recovered_record = _find_record(records, "after.inner.error")
    assert recovered_record["span_name"] == "outer"
    assert recovered_record["span_depth"] == 0
    assert recovered_record["span_path"] == "1:outer"


@pytest.mark.asyncio
async def test_asyncio_create_task_inherits_parent_span_and_keeps_siblings_isolated(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.JSON, enqueue=False)
    results: dict[str, tuple[int, str, int]] = {}

    async def worker(name: str, delay: float) -> None:
        await anyio.sleep(delay)
        async with span_context(name, span_type="service") as worker_span:
            results[name] = (worker_span.span_seq, worker_span.span_path, worker_span.span_depth)
            loguru_logger.info(f"asyncio.{name}")

    async with span_context("root", span_type="request") as root_span:
        left_task = asyncio.create_task(worker("left", 0.05))
        right_task = asyncio.create_task(worker("right", 0.0))
        await asyncio.gather(left_task, right_task)

    assert root_span.span_path == "1:root"
    assert {results["left"][0], results["right"][0]} == {2, 3}
    assert results["left"][1].startswith("1:root/")
    assert results["right"][1].startswith("1:root/")
    assert results["left"][2] == 1
    assert results["right"][2] == 1

    loguru_logger.complete()
    records = _read_json_records(_default_log_file(base_log_dir))
    left_record = _find_record(records, "asyncio.left")
    right_record = _find_record(records, "asyncio.right")

    assert left_record["span_path"] == results["left"][1]
    assert right_record["span_path"] == results["right"][1]
    assert "right" not in left_record["span_path"]
    assert "left" not in right_record["span_path"]


@pytest.mark.asyncio
async def test_anyio_task_group_shares_seq_runtime_without_stack_pollution(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.JSON, enqueue=False)
    results: dict[str, tuple[int, str, int]] = {}

    async def worker(name: str, delay: float) -> None:
        await anyio.sleep(delay)
        async with span_context(name, span_type="service") as worker_span:
            results[name] = (worker_span.span_seq, worker_span.span_path, worker_span.span_depth)
            loguru_logger.info(f"task-group.{name}")

    async with span_context("root", span_type="request"):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(worker, "alpha", 0.05)
            task_group.start_soon(worker, "beta", 0.0)

    assert {results["alpha"][0], results["beta"][0]} == {2, 3}
    assert results["alpha"][2] == 1
    assert results["beta"][2] == 1

    loguru_logger.complete()
    records = _read_json_records(_default_log_file(base_log_dir))
    alpha_record = _find_record(records, "task-group.alpha")
    beta_record = _find_record(records, "task-group.beta")

    assert alpha_record["span_path"] == results["alpha"][1]
    assert beta_record["span_path"] == results["beta"][1]
    assert alpha_record["span_path"].startswith("1:root/")
    assert beta_record["span_path"].startswith("1:root/")


@pytest.mark.asyncio
async def test_text_formatter_only_adds_span_segment_for_active_span(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.TEXT, enqueue=False)

    async with span_context("text-root", span_type="service"):
        loguru_logger.info("text.inside")
    loguru_logger.info("text.outside")

    loguru_logger.complete()
    lines = _default_log_file(base_log_dir).read_text(encoding="utf-8").splitlines()

    inside_line = next(line for line in lines if "text.inside" in line)
    outside_line = next(line for line in lines if "text.outside" in line)

    assert "1 text-root d=0 1:text-root" in inside_line
    assert "1 text-root d=0 1:text-root" not in outside_line


@pytest.mark.asyncio
async def test_enqueue_true_keeps_span_fields_because_patcher_runs_before_queue(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.JSON, enqueue=True)

    loguru_logger.info("outside.queue")
    async with span_context("queued", span_type="llm"):
        loguru_logger.info("inside.queue")

    loguru_logger.complete()
    records = _read_json_records(_default_log_file(base_log_dir))

    outside_record = _find_record(records, "outside.queue")
    assert outside_record["span_seq"] is None
    assert outside_record["span_name"] is None
    assert outside_record["span_type"] is None
    assert outside_record["span_depth"] is None
    assert outside_record["span_path"] is None

    inside_record = _find_record(records, "inside.queue")
    assert inside_record["span_seq"] == 1
    assert inside_record["span_name"] == "queued"
    assert inside_record["span_type"] == "llm"
    assert inside_record["span_depth"] == 0
    assert inside_record["span_path"] == "1:queued"


def test_with_span_rejects_sync_function():
    with pytest.raises(TypeError, match="async def only"):

        @with_span(span_type="service")
        def sync_func():
            return "not allowed"


def test_span_context_rejects_sync_with_usage():
    with pytest.raises(TypeError, match="async with"):
        with span_context("sync", span_type="service"):
            pass


def test_time_field_uses_iso_8601_format(tmp_path):
    _, base_log_dir = _configure_logger(tmp_path, log_format=LogFormat.JSON, enqueue=False)

    loguru_logger.info("time.check")
    loguru_logger.complete()

    record = _find_record(_read_json_records(_default_log_file(base_log_dir)), "time.check")
    parsed_time = datetime.fromisoformat(record["time"].replace("Z", "+00:00"))

    assert parsed_time.tzinfo is not None
    assert parsed_time.tzinfo == UTC
