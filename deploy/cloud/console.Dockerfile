# Imagen de la consola SOC: build de Vite + Caddy (TLS y proxy).
# Contexto de build = RAÍZ del repo:  docker build -f deploy/cloud/console.Dockerfile .
#
# `VITE_API_BASE_URL=/api` es lo que hace que la consola hable con su propio origen:
# sin CORS, sin preflight y con el WebSocket saliendo por `wss://host/api/ws`.
#
# `VITE_DEV_TOKEN_ENABLED=false` se declara EXPLÍCITAMENTE (T-1.62): antes se
# confiaba en "no definirla", y el `web/.env` local se colaba por `COPY web web`
# (no había .dockerignore) → la consola de producción pintaba el panel LOGIN DEV
# contra un endpoint que la nube no monta (404). Lo que no se declara, se hereda.
#
# La etapa de build corre en la plataforma del HOST ($BUILDPLATFORM): `dist/` es
# JS/CSS independiente de arquitectura, así que node+vite no pagan la emulación
# QEMU al cross-compilar para el EC2 Graviton — solo la etapa final de Caddy es arm64.

FROM --platform=$BUILDPLATFORM node:22-slim AS build

WORKDIR /repo

# El SDK instala SUS dependencias dentro de la imagen (T-1.62). Antes no lo hacía:
# `COPY shared/sdk-ts` arrastraba el node_modules del laptop y el `tsc` del web
# resolvía @hey-api/client-fetch desde ahí. Con .dockerignore excluyendo
# node_modules eso se cayó — señal de que el build nunca fue reproducible.
COPY shared/sdk-ts/package.json shared/sdk-ts/package-lock.json shared/sdk-ts/
RUN cd shared/sdk-ts && npm ci

# @takab/design-tokens (T-2.01): TS crudo, SIN dependencias ni lock ni build
# (`main`/`types` = src/index.ts). Su package.json debe existir antes del `npm ci`
# del web para que resuelva el `file:../shared/design-tokens`; el árbol completo
# se copia más abajo para que tsc/vite lean el source. Sin esto la consola no
# compila (TS2307: Cannot find module '@takab/design-tokens').
COPY shared/design-tokens/package.json shared/design-tokens/

COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci

COPY shared/sdk-ts shared/sdk-ts
COPY shared/design-tokens shared/design-tokens
# `shared/fixtures` (T-2.75.a): la MISMA fixture la leen los dos lados del
# contrato de canales — `api/tests/api/test_notify_channels.py` y el test de
# `NotificationChannels.tsx`. El `build` de aquí corre `tsc --noEmit`, que
# typechequea también los `*.test.tsx`, así que sin este COPY la consola no
# compila (TS2307) aunque la app no use la fixture para nada.
#
# Por qué se descubrió en un despliegue y no antes: `make lint` y el job `web`
# typechequean el árbol COMPLETO del checkout, donde `shared/fixtures/` existe.
# Esta imagen solo ve lo que se copia, así que era la única superficie capaz de
# verlo — y solo la construye `make cloud-images`. El gate que lo impide repetir
# es `web/src/consoleImageCensus.test.ts`.
COPY shared/fixtures shared/fixtures
# [T-5.10] El vocabulario de PROCEDENCIA de la cifra sísmica externa, por la misma
# razón exacta: `web/src/features/triage/procedencia.ts` lo importa, el `build`
# corre `tsc --noEmit` y sin este COPY la imagen muere con TS2307 tras varios
# minutos. Es JSON —y no un módulo— porque el panel del gabinete lo comparte y se
# sirve como un archivo estático desde el Pi, sin build que pueda importar nada.
#
# Lo cazó `consoleImageCensus` antes de gastar el build, que es justo para lo que
# se escribió.
COPY shared/glossary shared/glossary
COPY web web

ARG VITE_COGNITO_AUTHORITY=""
ARG VITE_COGNITO_CLIENT_ID=""
ARG VITE_COGNITO_DOMAIN=""
ARG VITE_COGNITO_REDIRECT_URI=""
ARG VITE_COGNITO_POST_LOGOUT_URI=""

ENV VITE_API_BASE_URL=/api \
    VITE_DEV_TOKEN_ENABLED=false \
    VITE_COGNITO_AUTHORITY=${VITE_COGNITO_AUTHORITY} \
    VITE_COGNITO_CLIENT_ID=${VITE_COGNITO_CLIENT_ID} \
    VITE_COGNITO_DOMAIN=${VITE_COGNITO_DOMAIN} \
    VITE_COGNITO_REDIRECT_URI=${VITE_COGNITO_REDIRECT_URI} \
    VITE_COGNITO_POST_LOGOUT_URI=${VITE_COGNITO_POST_LOGOUT_URI}

RUN cd web && npm run build -- --mode production

FROM caddy:2-alpine

COPY --from=build /repo/web/dist /srv
COPY deploy/cloud/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80 443
