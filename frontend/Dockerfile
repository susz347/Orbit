# Orbit Frontend — Next.js 16 Web UI
# Multi-stage build for minimal production image

FROM node:20-alpine AS builder

WORKDIR /app

# 依赖层缓存
COPY package.json package-lock.json* ./
RUN npm ci

# 构建
COPY . .
RUN npm run build

# ── 生产镜像 ──
FROM node:20-alpine AS runner

WORKDIR /app

RUN addgroup --system --gid 1001 orbit && \
    adduser --system --uid 1001 orbit

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER orbit

EXPOSE 3000

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

CMD ["node", "server.js"]
