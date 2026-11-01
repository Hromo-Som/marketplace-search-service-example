#!/bin/bash

set -e

uv run alembic upgrade head

uv run python -m bin.consumer &
CONSUMER_PID=$!

uv run python -m bin.api