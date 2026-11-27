# Misma versión de Python con la que se prueban los tests (ver requirements.txt).
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system paktai && useradd --system --gid paktai paktai
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY scripts ./scripts
COPY sql ./sql
COPY data/bronze/public/amie_abandono.csv data/bronze/public/enemdu_hogar.csv data/bronze/public/ineval_factores.csv ./data/bronze/public/
USER paktai
EXPOSE 8000
CMD ["uvicorn", "backend.production.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
