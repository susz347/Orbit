# Docker 容器化

> 一套 `docker compose up -d` 即可在任何机器上启动完整服务。

---

## 三份文件

| 文件 | 用途 |
|------|------|
| `backend/Dockerfile` | Python 后端镜像 |
| `frontend/Dockerfile` | Node.js 前端镜像（多阶段构建） |
| `docker-compose.yml` | 一键编排 |

---

## 后端 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

# Python 依赖（分层缓存：修改代码不需要重新装包）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 数据目录
RUN mkdir -p /app/data/chroma_db /app/data/uploads

# 非 root 用户（安全基线）
RUN useradd -m -u 1000 orbit && chown -R orbit:orbit /app
USER orbit

EXPOSE 8001

# Docker 自动健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
```

关键设计点：

- **分层缓存**：先 COPY requirements.txt 再 pip install，改代码不需要重装包
- **非 root 用户**：`USER orbit`，即使容器被突破也无法拿到宿主机 root
- **HEALTHCHECK**：Docker 每 30 秒调用 `/health`，3 次失败自动标记 unhealthy

---

## 前端 Dockerfile（多阶段构建）

```dockerfile
# ── 构建阶段 ──
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# ── 生产镜像（只复制构建产物）──
FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup --system --gid 1001 orbit && \
    adduser --system --uid 1001 orbit

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER orbit
EXPOSE 3000
CMD ["node", "server.js"]
```

关键设计点：

- **多阶段构建**：builder 镜像包含全部 node_modules 和源码（大），runner 镜像只复制编译好的 standalone 产物（小）
- Next.js standalone 模式：`server.js` 包含了所有运行时依赖，不需要 `node_modules`

---

## docker-compose.yml

```yaml
services:
  backend:
    build: ./backend
    ports: ["8001:8001"]
    volumes:
      - orbit_data:/app/data           # 持久化
      - ./backend/.env:/app/.env:ro    # 只读挂载
    environment:
      - ENV=${ENV:-production}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "..."]
      interval: 30s

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8001
    depends_on:
      backend:
        condition: service_healthy    # 等后端健康后才启动
    restart: unless-stopped

volumes:
  orbit_data:    # ChromaDB、SQLite、uploads 持久化
```

**`depends_on: condition: service_healthy`** 是关键——确保后端数据库初始化完毕、embedding 模型预热完成后，前端才接收流量。

---

## 使用方式

```bash
# 启动
docker compose up -d

# 查看状态
docker compose ps

# 查看日志（带结构化 JSON）
docker compose logs -f backend

# 停止
docker compose down
```
