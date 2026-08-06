FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 openkey \
    && useradd --system --uid 10001 --gid openkey --home-dir /app --shell /usr/sbin/nologin openkey

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=openkey:openkey alembic.ini .
COPY --chown=openkey:openkey alembic ./alembic
COPY --chown=openkey:openkey app ./app

USER openkey

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
