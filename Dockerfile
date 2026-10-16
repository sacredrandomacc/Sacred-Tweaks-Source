FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY server /app/server
RUN useradd --uid 10001 --create-home sacred && mkdir /data && chown sacred:sacred /data
USER sacred
EXPOSE 8765
VOLUME ["/data"]
CMD ["python", "-m", "server", "--host", "0.0.0.0", "--port", "8765", "--db", "/data/sacred.db"]
