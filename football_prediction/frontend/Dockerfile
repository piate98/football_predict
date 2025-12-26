# ---------- Build stage ----------
FROM node:20-alpine AS build
WORKDIR /app

# Install deps
COPY package*.json ./
RUN npm ci

# Build
COPY . .
RUN npm run build

# ---------- Serve stage ----------
FROM nginx:alpine

# Static site
COPY --from=build /app/dist /usr/share/nginx/html

# Nginx config (proxy /api -> backend)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]