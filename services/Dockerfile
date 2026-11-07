# Shared image recipe for every Python service. Build from the repo root:
#   docker build -f services/Dockerfile --build-arg SERVICE=identity .
FROM python:3.12-slim
ARG SERVICE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.12.5
WORKDIR /srv
COPY libs/common /srv/libs/common
COPY services/${SERVICE} /srv/services/${SERVICE}
WORKDIR /srv/services/${SERVICE}
RUN uv sync --frozen --no-dev && useradd --system --uid 10001 app
ENV PATH="/srv/services/${SERVICE}/.venv/bin:$PATH"
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
