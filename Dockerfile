FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

RUN addgroup --system django && adduser --system --ingroup django --home /app django
RUN mkdir -p /app/data && chown -R django:django /app
USER django

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
