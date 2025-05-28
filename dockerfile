FROM alpine:3.21

WORKDIR /src
RUN mkdir /config

COPY src/ .
COPY src/entrypoint.sh /entrypoint.sh

RUN apk update && apk upgrade
RUN apk add docker-cli python3 py3-pip tzdata

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip3 install discord.py && pip3 install prettytable

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "bot.py"]