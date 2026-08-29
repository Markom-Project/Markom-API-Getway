FROM python:3.12-slim AS builder

WORKDIR /app

COPY markom_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY markom_gateway/ markom_gateway/

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY markom_gateway/ markom_gateway/

ENV PYTHONPATH="/app"
ENV MARKOM_GATEWAY_MODE="true"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "markom_gateway.admin_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
