# Imagen de la consola SOC: build de Vite + Caddy (TLS y proxy).
# Contexto de build = RAÍZ del repo:  docker build -f deploy/cloud/console.Dockerfile .
#
# `VITE_API_BASE_URL=/api` es lo que hace que la consola hable con su propio origen:
# sin CORS, sin preflight y con el WebSocket saliendo por `wss://host/api/ws`.
#
# `VITE_DEV_TOKEN_ENABLED` NO se define: el panel de login dev no existe en la nube.

FROM node:22-slim AS build

WORKDIR /repo

COPY shared/sdk-ts shared/sdk-ts
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci

COPY web web

ARG VITE_COGNITO_AUTHORITY=""
ARG VITE_COGNITO_CLIENT_ID=""
ARG VITE_COGNITO_DOMAIN=""
ARG VITE_COGNITO_REDIRECT_URI=""
ARG VITE_COGNITO_POST_LOGOUT_URI=""

ENV VITE_API_BASE_URL=/api \
    VITE_COGNITO_AUTHORITY=${VITE_COGNITO_AUTHORITY} \
    VITE_COGNITO_CLIENT_ID=${VITE_COGNITO_CLIENT_ID} \
    VITE_COGNITO_DOMAIN=${VITE_COGNITO_DOMAIN} \
    VITE_COGNITO_REDIRECT_URI=${VITE_COGNITO_REDIRECT_URI} \
    VITE_COGNITO_POST_LOGOUT_URI=${VITE_COGNITO_POST_LOGOUT_URI}

RUN cd web && npm run build

FROM caddy:2-alpine

COPY --from=build /repo/web/dist /srv
COPY deploy/cloud/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80 443
