FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/uploads /app/static

COPY . .

EXPOSE 8005

CMD ["python", "main.py"]
