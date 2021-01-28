ARG BASE_IMAGE
FROM $BASE_IMAGE

WORKDIR /app

RUN pip install -U warcio wacz

COPY /app/ /app/

COPY /uwsgi/ /uwsgi/

ARG BASE_IMAGE
FROM $BASE_IMAGE

