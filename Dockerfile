FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/

RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
