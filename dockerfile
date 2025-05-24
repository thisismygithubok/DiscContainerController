FROM alpine:3.21
WORKDIR /src

COPY src/ .

RUN apk update && apk upgrade
RUN apk add --no-cache python3 py3-pip

RUN python3 -m pip install -U discord.py

