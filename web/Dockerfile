# syntax=docker/dockerfile:1
# Barterly web (Next.js standalone) for Cloud Run.
# Environment-specific values are read at runtime from server code (process.env),
# never baked in with NEXT_PUBLIC_*, so one image can be promoted staging -> production.

FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-slim AS build
WORKDIR /app
# The commit is the Sentry release; source maps upload when the sentry_auth_token
# build secret is given (deploy.yml), then next.config deletes them from the output.
ARG GIT_SHA=unknown
ARG SENTRY_ORG=""
ARG SENTRY_PROJECT_WEB=""
# Media CDN hosts for the CSP (docs/edge.md); the image serves staging and production.
ARG MEDIA_CDN_ORIGINS=""
ENV NEXT_TELEMETRY_DISABLED=1 \
    MEDIA_CDN_ORIGINS=${MEDIA_CDN_ORIGINS} \
    SENTRY_RELEASE=${GIT_SHA} \
    SENTRY_ORG=${SENTRY_ORG} \
    SENTRY_PROJECT_WEB=${SENTRY_PROJECT_WEB}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN --mount=type=secret,id=sentry_auth_token,required=false \
    SENTRY_AUTH_TOKEN="$(cat /run/secrets/sentry_auth_token 2>/dev/null || true)" npm run build

FROM node:24-slim AS runtime
WORKDIR /app
ARG GIT_SHA=unknown
ENV SENTRY_RELEASE=${GIT_SHA} \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8080 \
    HOSTNAME=0.0.0.0
# The server runs with node alone: drop the npm and corepack the base image bundles
# (they carried known vulnerabilities, and an attacker could use them).
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
    /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 8080
CMD ["node", "server.js"]
