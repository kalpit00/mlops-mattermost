FROM python:3.11-slim-bookworm

WORKDIR /app

COPY serving/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY serving ./serving

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "serving.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
