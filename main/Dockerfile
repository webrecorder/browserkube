ARG BASE_IMAGE
FROM $BASE_IMAGE

ENV APP_MODULE browserkube
ENV PORT 80

WORKDIR /app/

CMD ./run.sh

COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY . /app/
