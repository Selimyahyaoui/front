FROM docker.artifactory-dogen.group.echonet/python:3.12

# Déclare les arguments proxy
ARG http_proxy
ARG https_proxy

ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy

# Configure pip pour Artifactory dogen avec token
RUN mkdir -p /etc && \
    echo "[global]" > /etc/pip.conf && \
    echo "index-url = https://selim.yahyaoui@externe.bnpparibas.com:cmVmdGtUoJAx0jE3ODI1NzEwMTM6UDZI@artifactory.am.echonet/artifactory/api/pypi/bnpp-group-dogen-pipy/pypi/simple" >> /etc/pip.conf && \
    echo "trusted-host = artifactory.am.echonet" >> /etc/pip.conf

# Debug : voir pip.conf
RUN cat /etc/pip.conf

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8010

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["python3", "-m", "uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8010"]
