FROM python:3.12

WORKDIR /middleware-dt

RUN pip install --no-cache-dir --upgrade pip setuptools
RUN apt-get update && \
    apt-get install -y iproute2 iputils-ping net-tools procps iptables curl tcpdump inetutils-traceroute dnsutils lsof nano less vim socat iperf3 netcat-openbsd && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

EXPOSE 8000

ENV DJANGO_SETTINGS_MODULE=middleware-dt.settings

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

