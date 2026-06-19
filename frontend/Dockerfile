# ---------------------------------------------------------------------------
# Stage 1: Builder — compile React app
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps first (better layer caching)
COPY package.json package-lock.json* ./
RUN npm ci --silent

# Copy source and build
COPY . .
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2: Runtime — serve via Nginx
# ---------------------------------------------------------------------------
FROM nginx:1.25-alpine AS runtime

LABEL org.opencontainers.image.title="ArchPilot Frontend"
LABEL org.opencontainers.image.description="React dashboard for repository intelligence"

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Custom nginx config with API proxy
COPY nginx.conf /etc/nginx/conf.d/archpilot.conf

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
