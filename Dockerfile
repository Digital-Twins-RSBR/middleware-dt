FROM python:3.12

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip setuptools

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

EXPOSE 8000

ENV DJANGO_SETTINGS_MODULE=middleware-dt.settings

CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]
