ARG BASE_IMAGE
FROM $BASE_IMAGE

RUN set -xe; \
    apk add --update xvfb;\
    rm -rf /var/cache/apk/*;

ENV DISPLAY ":99"
ENV GEOMETRY "1360x1020x16"

CMD ["/app/run.sh"]

WORKDIR /app/
COPY . /app/
