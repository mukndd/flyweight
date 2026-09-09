# Flyweight frontend (apps/web).
#
# Build context must be the repository root, because the frontend imports
# the shared packages/protocol and packages/sim workspaces. Build with:
#   docker build -f apps/web/Dockerfile -t flyweight-web .
#
# Runtime env (all optional, all validated by scripts/serve_web.mjs):
#   PORT                       listen port (default 5180)
#   FLYWEIGHT_ENV              "production" enables 0.0.0.0 binding and
#                               requires HTTPS-only FLYWEIGHT_PUBLIC_ORIGINS
#   FLYWEIGHT_BIND_HOST        127.0.0.1 (default) or 0.0.0.0 in production
#   FLYWEIGHT_PUBLIC_ORIGINS   comma-separated exact allowed origins
#   BRAIN_UPSTREAM              optional http(s) URL of the brain service;
#                               when set, /brain/ws is proxied to it so the
#                               browser never needs a separate backend host

FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/dist/web ./dist/web
COPY --from=build /app/scripts/serve_web.mjs ./scripts/serve_web.mjs
USER node
EXPOSE 5180
CMD ["node", "scripts/serve_web.mjs"]
