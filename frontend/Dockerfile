FROM node:26-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

# WORKDIR and COPY both run as root at build time, so /app is root-owned
# unless fixed here — docker-compose.yml runs this container as the "node"
# user (uid 1000, built into this base image) to keep bind-mounted files
# host-writable, and Vite itself needs to write into /app too (a
# config-load timestamp file), not just the mounted src/.
RUN chown -R node:node /app

CMD ["npm", "run", "dev"]
