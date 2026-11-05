import uvicorn

from src.fastapi import create_app
from src.trace_context import get_logging_config

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "bin.api:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        access_log=False,
        log_config=get_logging_config(),
    )
