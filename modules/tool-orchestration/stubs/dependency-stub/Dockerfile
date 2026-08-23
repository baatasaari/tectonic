FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"
COPY app.py .
EXPOSE 9104
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9104"]
