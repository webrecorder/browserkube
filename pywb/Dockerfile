ARG BASE_IMAGE
FROM $BASE_IMAGE

WORKDIR /app

RUN pip install -U "git+https://github.com/webrecorder/wacz-format.git@master#egg=wacz&subdirectory=py-wacz"

RUN pip install -U warcio

COPY config.yaml /app/

COPY captureapp.py /app/

COPY uwsgi.ini /uwsgi/


