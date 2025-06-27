FROM docker.artifactory-dogen.group.echonet/python:3.12

# Déclare les arguments proxy et Artifactory
ARG http_proxy
ARG https_proxy
ARG ARTI_USER
ARG ARTI_PASS

# Passe les variables proxy au conteneur si nécessaire
ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy

# Configure pip pour pointer vers Artifactory dogen
RUN mkdir -p /etc && \
    echo "[global]" > /etc/pip.conf && \
    echo "index-url = https://${ARTI_USER}:${ARTI_PASS}@repo.artifactory-dogen.group.echonet.net.intra/artifactory/api/pypi/pypi/simple" >> /etc/pip.conf && \
    echo "trusted-host = repo.artifactory-dogen.group.echonet.net.intra" >> /etc/pip.conf

# Définir le dossier de travail
WORKDIR /app

# Copier requirements.txt avant installation
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier tout le projet
COPY . .

# Exposer le port de l'application
EXPOSE 8010

# Lancer l'app via uvicorn
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["python3", "-m", "uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8010"]
