FROM python:3.13-slim

WORKDIR /app

# tzdata: python:3.13-slim không kèm sẵn /usr/share/zoneinfo — thiếu nó thì
# biến TZ=Asia/Ho_Chi_Minh (docker-compose.yml) bị bỏ qua, container vẫn UTC.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev tzdata && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
