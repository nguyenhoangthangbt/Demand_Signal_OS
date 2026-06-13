# DemandSignalOS — THIN trust-gate API image.
#
# Build context is the platforms_os repo root (so the shared packages under
# packages/ are reachable), mirroring simulation_os/Dockerfile — but LIGHT.
#
# Critical: this image installs ONLY the light deps the trust-gate surface
# needs — ops_schemas + excel_io + trust_gate + fastapi + uvicorn. It does NOT
# `pip install demand_signal_os`, so the heavy forecasting stack
# (scipy / statsforecast / hierarchicalforecast / lightgbm / pandas / numpy)
# is never pulled. The `demand_signal_os.api` module is made importable by
# COPYing the DSO src tree onto PYTHONPATH, NOT by installing the package.
# The api code imports only trust_gate/excel_io/fastapi inside its handlers
# (never `import demand_signal_os` of the forecasting modules), so the heavy
# transitive deps are not required at import time.
#
#   build:  docker build -f Demand_Signal_OS/Dockerfile -t dso-api .
#           (with the platforms_os repo root as build context)

# ---------------------------------------------------------------------------
# Stage 1: Builder — install the 3 light packages + fastapi + uvicorn
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /build

# Shared packages (platforms_os/packages/). Install all three local-path deps
# together with fastapi + uvicorn in ONE pip invocation. trust_gate depends on
# ops_schemas + excel_io; pip resolves the local paths together.
COPY packages/ops_schemas/pyproject.toml ./ops_schemas_pkg/
COPY packages/ops_schemas/src/ ./ops_schemas_pkg/src/

COPY packages/excel_io/pyproject.toml packages/excel_io/README.md ./excel_io_pkg/
COPY packages/excel_io/src/ ./excel_io_pkg/src/

COPY packages/trust_gate/pyproject.toml ./trust_gate_pkg/
COPY packages/trust_gate/src/ ./trust_gate_pkg/src/

RUN pip install --no-cache-dir --prefix=/install \
    "./ops_schemas_pkg/" "./excel_io_pkg/" "./trust_gate_pkg/" \
    "fastapi" "uvicorn[standard]"

# ---------------------------------------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

LABEL maintainer="DemandSignalOS Team"
LABEL description="DemandSignalOS — thin trust-gate API (signed forecast receipts)"

RUN groupadd -r dso && useradd -r -g dso -d /app dso

WORKDIR /app

# Light deps installed in the builder.
COPY --from=builder /install /usr/local

# The DSO `api` module — copied (NOT pip-installed) so heavy deps are skipped.
# Only src/demand_signal_os/api is needed at runtime, but we copy the whole
# src tree so `demand_signal_os` is a proper importable package on PYTHONPATH.
COPY Demand_Signal_OS/src/ /app/src/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check hits the thin API's own health route.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

USER dso

EXPOSE 8000

ENTRYPOINT ["uvicorn", "demand_signal_os.api.app:create_app", "--factory", \
    "--host", "0.0.0.0", "--port", "8000"]
