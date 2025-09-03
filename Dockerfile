# ✅ Use your custom Python image from Artifactory
FROM artifactory.am.echonet/amic-docker-virtual/amic/base/amic-python:3.12

# ✅ Arguments for Artifactory authentication
ARG ARTI_USER
ARG ARTI_PASS

# ✅ Define Artifactory hostname
ENV ARTIFACTORY_HOSTNAME="artifactory.am.echonet"

# ✅ Configure pip to use Artifactory PyPI virtual repo
RUN echo "[global]" > /usr/local/pip.conf \
    && echo "index-url = https://${ARTI_USER}:${ARTI_PASS}@${ARTIFACTORY_HOSTNAME}/artifactory/api/pypi/amic-python-virtual/simple" >> /usr/local/pip.conf \
    && echo "trusted-host = ${ARTIFACTORY_HOSTNAME}" >> /usr/local/pip.conf

# ✅ Copy requirements
COPY requirements.txt /app/requirements.txt

# ✅ Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# ✅ Copy your application code
COPY . /app

# ✅ Set working directory
WORKDIR /app

# dossier pour CSV/JSON (même sans PVC)
RUN useradd -m appuser && mkdir -p /app/app/static/uploads /app/app/static/json && chown -R appuser:appuser /app
USER appuser

# ✅ Expose application port
EXPOSE 8010

# ✅ Launch your app with gunicorn
CMD ["gunicorn", "-b", ":8010", "app:app"]
