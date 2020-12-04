ARG BASE_IMAGE
FROM $BASE_IMAGE

WORKDIR /app

RUN pip install -U warcio "git+https://github.com/webrecorder/wacz-format.git@master#egg=wacz&subdirectory=py-wacz"

COPY . /app/
