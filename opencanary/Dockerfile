FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    gcc libssl-dev libffi-dev python3-dev \
    && pip install opencanary \
    && apt-get clean
COPY opencanary.conf /etc/opencanaryd/opencanary.conf
CMD ["opencanaryd", "--dev", "--uid=0", "--gid=0"]
