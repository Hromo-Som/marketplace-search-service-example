import logging
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.trace_context import TraceIdMiddleware, configure_logging, get_trace_id


@pytest.mark.asyncio
async def test_middleware_uses_incoming_trace_id() -> None:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/trace")
    async def read_trace_id() -> dict[str, str | None]:
        return {"trace_id": get_trace_id()}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/trace", headers={"X-Trace-Id": "trace-123"})

    assert response.json() == {"trace_id": "trace-123"}
    assert response.headers["X-Trace-Id"] == "trace-123"
    assert get_trace_id() is None


@pytest.mark.asyncio
async def test_middleware_generates_trace_id_when_missing() -> None:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/trace")
    async def read_trace_id() -> dict[str, str | None]:
        return {"trace_id": get_trace_id()}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/trace")

    trace_id = response.headers["X-Trace-Id"]
    assert response.json() == {"trace_id": trace_id}
    assert str(UUID(trace_id)) == trace_id
    assert get_trace_id() is None


@pytest.mark.asyncio
async def test_request_logs_include_trace_id() -> None:
    configure_logging()
    records: list[str] = []
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s [trace_id=%(trace_id)s]"))
    handler.addFilter(lambda record: record.name != "httpx")
    handler.emit = lambda record: records.append(handler.format(record))
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/trace")
    async def read_trace_id() -> dict[str, str | None]:
        logging.getLogger("trace-test").info("handling request")
        return {"trace_id": get_trace_id()}

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/trace", headers={"X-Trace-Id": "trace-log"})
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(previous_level)

    assert len(records) >= 2
    assert all("[trace_id=trace-log]" in record for record in records)
