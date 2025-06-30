FROM docker.artifactory-dogen.group.echonet/python:3.12

# Arguments
ARG ARTI_USER
ARG ARTI_PASS
ARG REPO_URL

# Définir la variable d'hostname
ENV ARTIFACTORY_HOSTNAME="repo.artifactory-dogen.group.echonet.net.intra"

# Configuration de pip.conf
RUN echo "[global]" > /usr/local/pip.conf \
    && echo "index-url = https://${ARTI_USER}:${ARTI_PASS}@${ARTIFACTORY_HOSTNAME}/artifactory/api/pypi/pypi/simple" >> /usr/local/pip.conf \
    && echo "trusted-host = ${ARTIFACTORY_HOSTNAME}" >> /usr/local/pip.conf

# Debug pip si besoin
RUN pip3 config --user debug

# Créer virtualenv (optionnel, si tu veux l’utiliser)
RUN python3 -m venv .venv

# Installer les requirements en global (avant virtualenv) 
# ou adapte le chemin vers ton venv si tu souhaites l'utiliser
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copier le code source
COPY ./ /app

WORKDIR /app

EXPOSE 8010

CMD ["gunicorn", "-b", ":8010", "app:app"]
