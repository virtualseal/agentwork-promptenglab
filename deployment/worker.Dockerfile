# Reviewed Linux/amd64 browser image, matching the Python Playwright package.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble@sha256:abf13b369f8829eb45e29df38d6c5221f7e7521649cb5d2de7989c82bdb574ad
# Image provisioning only; all application installs/builds/runtime run as UID502.
RUN groupadd --gid 502 agentwork && useradd --uid 502 --gid 502 --create-home agentwork && mkdir -p /app /data/worker && chown 502:502 /app /data/worker
USER 502:502
ENV HOME=/home/agentwork PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 THURSDAY_CONFIG=/app/deployment/worker.config.json
WORKDIR /app
RUN python3 -m venv --without-pip /home/agentwork/venv && pip --python /home/agentwork/venv/bin/python install --no-cache-dir --no-deps playwright==1.60.0 pyee==13.0.1 greenlet==3.5.6 typing-extensions==4.16.0
COPY --chown=502:502 app /app/app
COPY --chown=502:502 run /app/run
COPY --chown=502:502 deployment/worker.py deployment/worker.config.json deployment/worker.Dockerfile /app/deployment/
CMD ["/usr/bin/python3", "-B", "deployment/worker.py"]
