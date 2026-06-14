FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

COPY . .

# Absolute API base baked into the build so the leaderboard SPA calls the
# public DSO API instead of the (nonexistent) same-origin /api/v1. Vite inlines
# VITE_* env at build time. Empty default keeps the old relative behaviour.
ARG VITE_DSO_API_BASE=""
ENV VITE_DSO_API_BASE=$VITE_DSO_API_BASE
RUN npm run build

FROM nginx:1.27-alpine AS runtime

LABEL maintainer="DemandSignalOS Team"
LABEL description="DemandSignalOS — v0.1 preview web UI"

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
