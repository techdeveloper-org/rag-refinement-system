# syntax=docker/dockerfile:1
#
# Static build + serve for the personal-tool SPA (frontend/, ADR-9: React+Vite).
# Stage 1 builds the SPA with Vite; stage 2 serves the static bundle with a
# non-root nginx. No secrets are baked: the only build arg is the PUBLIC API
# base URL the browser calls (VITE_API_BASE_URL). TLS is terminated upstream at
# the reverse proxy / load balancer, not here.

# ---- Build stage ----
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# ---- Serve stage: non-root nginx serving the immutable bundle ----
FROM nginxinc/nginx-unprivileged:1.27-alpine AS serve

# nginx-unprivileged already runs as uid 101 (non-root) and listens on 8080.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
