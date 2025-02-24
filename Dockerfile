FROM python:3.12

WORKDIR /middleware-dt

RUN pip install --no-cache-dir --upgrade pip setuptools

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

EXPOSE 8000

ENV DJANGO_SETTINGS_MODULE=middleware-dt.settings

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

