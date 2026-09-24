FROM python:3.12-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1
WORKDIR /loadtest
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY *.py ./
RUN mkdir -p results
ENTRYPOINT ["locust"]
