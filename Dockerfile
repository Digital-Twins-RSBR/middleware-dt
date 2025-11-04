FROM python:3.12

WORKDIR /middleware-dt

RUN pip install --no-cache-dir --upgrade pip setuptools
RUN apt-get update && \
    apt-get install -y iproute2 iputils-ping net-tools procps iptables curl tcpdump inetutils-traceroute dnsutils lsof nano less vim socat iperf3 netcat-openbsd redis-server redis-tools postgresql-client && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

# Criar link simbólico para o módulo Python funcionar corretamente
RUN ln -s /middleware-dt/middleware-dt /middleware-dt/middleware_dt

EXPOSE 8000

ENV DJANGO_SETTINGS_MODULE=middleware_dt.settings

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

