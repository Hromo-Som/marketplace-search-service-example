import contextvars
import copy
import logging
import logging.config
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import AccessFormatter, DefaultFormatter

TRACE_ID_HEADER = b"x-trace-id"
logger = logging.getLogger(__name__)


class TraceIdDefaultFormatter(DefaultFormatter):
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        trace_id = getattr(record, "trace_id", "-")
        return "\n".join(
            f"{line} [trace_id={trace_id}]" for line in formatted.splitlines()
        )


class TraceIdAccessFormatter(AccessFormatter):
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        trace_id = getattr(record, "trace_id", "-")
        return "\n".join(
            f"{line} [trace_id={trace_id}]" for line in formatted.splitlines()
        )


trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


def get_trace_id() -> str | None:
    return trace_id_var.get()


def set_trace_id(trace_id: str | None) -> contextvars.Token[str | None]:
    return trace_id_var.set(trace_id)


def configure_logging() -> None:
    logging.captureWarnings(True)
    previous_factory = logging.getLogRecordFactory()

    def record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        record.trace_id = trace_id_var.get() or "-"
        return record

    logging.setLogRecordFactory(record_factory)
    logging.config.dictConfig(get_logging_config())


def get_logging_config() -> dict[str, object]:
    config = copy.deepcopy(LOGGING_CONFIG)
    config["formatters"]["default"]["()"] = "src.trace_context.TraceIdDefaultFormatter"
    config["formatters"]["access"]["()"] = "src.trace_context.TraceIdAccessFormatter"
    config["root"] = {"handlers": ["default"], "level": "INFO"}
    return config


class TraceIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        trace_id = (
            headers.get(TRACE_ID_HEADER, b"").decode("ascii", errors="ignore").strip()
        ) or str(uuid4())
        token = trace_id_var.set(trace_id)
        status_code = 500

        async def send_with_trace_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((TRACE_ID_HEADER, trace_id.encode("ascii")))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            logger.info(
                "request %s %s completed with status %s",
                scope["method"],
                scope["path"],
                status_code,
            )
            trace_id_var.reset(token)
