FROM python:3.11-slim
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY . .
ENV PORT=7860
EXPOSE 7860
CMD uvicorn api:app --host 0.0.0.0 --port ${PORT}
