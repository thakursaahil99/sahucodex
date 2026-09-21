# SahuCodeX web (Next.js). Build context is the repository root:
#   docker build -f infrastructure/docker/web.Dockerfile -t sahucodex-web .
#
# npm workspaces: apps/web depends on packages/shared, so the lockfile and both package.json
# files are needed to install. Requests to /api are routed to the backend by Caddy, so the web
# container needs no knowledge of the API address.

FROM node:24-slim AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
RUN npm ci

FROM deps AS build
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/web apps/web
COPY packages/shared packages/shared
RUN npm run build -w @sahucodex/web

FROM node:24-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /repo
COPY --from=build --chown=node:node /repo/package.json ./
COPY --from=build --chown=node:node /repo/node_modules ./node_modules
COPY --from=build --chown=node:node /repo/apps/web ./apps/web
COPY --from=build --chown=node:node /repo/packages/shared ./packages/shared

USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/healthz').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["npm", "run", "start", "-w", "@sahucodex/web", "--", "-H", "0.0.0.0", "-p", "3000"]
