docker build \
  --build-arg ARTI_USER=h47994 \
  --build-arg ARTI_PASS='Luffyselim123456@' \
  -t myimage .
# Fetch token
TOKEN=$(cat ~/.bluemix/config.json | jq -r .IAMRefreshToken)

# Login
docker login -u iamrefresh -p "$TOKEN" fr2.icr.io

# Tag
docker tag bmaasimage:latest fr2.icr.io/reg-r1e0021000650/bmaasimage:latest

# Push
docker push fr2.icr.io/reg-r1e0021000650/bmaasimage:latest
