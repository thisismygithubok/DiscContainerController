FROM alpine:3.24

WORKDIR /src
RUN mkdir /config

COPY src/ .
COPY src/entrypoint.sh /entrypoint.sh

# Official static docker CLI: Alpine's docker-cli package lags behind on CVE fixes
COPY --from=docker:29.9.1-cli /usr/local/bin/docker /usr/local/bin/docker
RUN apk add python3 tzdata su-exec

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# pip is only needed at build time; removing it drops its vendored urllib3/msgpack CVEs
RUN pip3 install discord.py prettytable "setuptools>=78.1.1" && pip3 uninstall -y pip

# Non-Root Docker
RUN addgroup -S -g 988 docker && \
    adduser -S -D -H -h /src -s /sbin/nologin -G docker -u 1000 nonroot && \
    adduser nonroot docker && \
    mkdir -p /config && \
    chown nonroot:docker /config && \
    chmod 2775 /config && \
    chown -R nonroot:docker /src /entrypoint.sh && \
    chmod -R 755 /src /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "bot.py"]