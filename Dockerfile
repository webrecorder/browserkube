#FROM oldwebtoday/shepherd:1.2.0-dev
FROM python:3.8

WORKDIR /app/

ADD requirements.txt /app/

RUN pip install -r requirements.txt

ADD main.py /app/
ADD cleanup.py /app/
ADD managers.py /app/
ADD run.sh /app/

CMD ./run.sh

#COPY app.py driver/embeds.json /app/
COPY templates/ /app/templates/
COPY static/ /app/static/
COPY replay/ /app/replay/

