FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملف السيرفر وباقي الملفات الضرورية ومجلد الكتب
COPY server.py .
COPY post_cover.png .
COPY books/ ./books/

ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
