FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 weather

COPY weatherChecker.py ./
COPY weather_checker ./weather_checker

USER weather

CMD ["python", "-m", "weather_checker.scheduler"]
