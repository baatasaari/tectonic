FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.32"
COPY scripts/product-slice-stubs/external_mocks.py /app/external_mocks.py
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 9200
CMD ["uvicorn", "external_mocks:app", "--host", "0.0.0.0", "--port", "9200"]

