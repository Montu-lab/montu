# deid: one image, runs offline. Build where the network is allowed; run with --network none.
#
#   GPU (default):  docker build -t deid:0.1.0 .
#   CPU:            docker build --build-arg BASE=python:3.11-slim-bookworm -t deid:0.1.0-cpu .
#
# Models are baked in from ./models (fetched at build time by scripts/fetch_models.py, SHA-256 in
# models/MODELS.lock). To mount them from a BPO-controlled store instead, build with --build-arg BAKE_MODELS=0
# and mount read-only at /opt/deid/models.
ARG BASE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
FROM ${BASE}

ARG BAKE_MODELS=1
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/deid
COPY pyproject.toml README.md ./
COPY src ./src
COPY policies ./policies
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install ".[asr]"
COPY models* ./models/
RUN if [ "$BAKE_MODELS" = "0" ]; then rm -rf ./models/*; fi

RUN useradd --system --uid 10001 deid && mkdir -p /in /out /work /private && chown deid /out /work
USER deid
ENV PATH=/opt/venv/bin:$PATH
ENV DEID_POLICY_DIR=/opt/deid/policies
ENTRYPOINT ["deid"]
CMD ["--help"]
