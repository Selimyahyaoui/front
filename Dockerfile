FROM docker.artifactory-dogen.group.echonet/python:3.12

ARG http_proxy
ARG https_proxy

ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy

RUN mkdir -p /etc && \
    echo "[global]" > /etc/pip.conf && \
    echo "index-url = https://selim.yahyaoui@externe.bnpparibas.com:cmVmdGtUoJAxE3ODI1NzEwMTM6UDZI@artifactory.am.echonet/artifactory/api/pypi/bnpp-group-dogen-pipy/pypi/simple" >> /etc/pip.conf && \
    echo "extra-index-url = https://pypi.org/simple" >> /etc/pip.conf && \
    echo "trusted-host = artifactory.am.echonet" >> /etc/pip.conf && \
    echo "trusted-host = pypi.org" >> /etc/pip.conf

RUN cat /etc/pip.conf

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8010

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["python3", "-m", "uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8010"]
