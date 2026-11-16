FROM python:3.12-alpine
RUN apk upgrade --no-cache \
    && addgroup -S -g 10001 app \
    && adduser -S -u 10001 -G app -H -s /sbin/nologin app
WORKDIR /srv
COPY attack.py .
USER 10001
EXPOSE 9000
CMD ["python", "-u", "attack.py", "--serve"]
