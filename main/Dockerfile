ARG BASE_IMAGE
FROM $BASE_IMAGE

WORKDIR /app/

ADD requirements.txt /app/

RUN pip install -r requirements.txt

ADD browserkube.py /app/
ADD cleanup.py /app/
ADD managers.py /app/
ADD run.sh /app/

ENV APP_MODULE browserkube
ENV PORT 80

CMD ./run.sh

#COPY app.py driver/embeds.json /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

