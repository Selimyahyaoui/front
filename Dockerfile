FROM docker.artifactory-dogen.group.echonet/python:3.12

ARG http_proxy
ARG https_proxy
ARG ARTI_USER
ARG ARTI_PASS

ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy

# Configurer pip avec Artifactory dogen
RUN pip config set global.index-url \
    https://${ARTI_USER}:${ARTI_PASS}@repo.artifactory-dogen.group.echonet.net.intra/artifactory/api/pypi/pypi/simple

RUN pip config set global.trusted-host repo.artifactory-dogen.group.echonet.net.intra

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8010

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["python3", "-m", "uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8010"]
