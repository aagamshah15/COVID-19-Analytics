# The simulator API image. Build from the repository root:
#   docker build -f api/Dockerfile -t simulator-api .
#   docker run --rm -p 8080:8080 simulator-api
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8080

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r api/requirements.txt

# Only the reference engine is copied in: the pipeline's other modules need pandas and friends.
COPY src/covid_pipeline/__init__.py src/covid_pipeline/__init__.py
COPY src/covid_pipeline/simulator/__init__.py \
     src/covid_pipeline/simulator/engine.py \
     src/covid_pipeline/simulator/season.py \
     src/covid_pipeline/simulator/scenario.py \
     src/covid_pipeline/simulator/analysis.py \
     src/covid_pipeline/simulator/
COPY api api

USER nobody
EXPOSE 8080
# One process: the request limits live in memory. Cloud Run sets PORT.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-access-log"]
