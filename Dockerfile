FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd -r runner && useradd -r -g runner runner
RUN mkdir -p /srv/data && chown runner:runner /srv/data
ENV DATABASE_URL=sqlite:////srv/data/skilllens.db SKILLLENS_DEV_KEY_FILE=/srv/data/dev.key
COPY ./app ./app
COPY ./models ./models
COPY ./training ./training
COPY ./migrations ./migrations
COPY ./alembic.ini ./alembic.ini
USER runner
EXPOSE 10000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --no-access-log"]
