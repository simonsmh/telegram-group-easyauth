FROM python:3-slim

WORKDIR /usr/src/app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
VOLUME /mnt
ENV CONFIG config.yml
ENV DOMAIN ""
EXPOSE 8080
CMD python main.py /mnt/$CONFIG
