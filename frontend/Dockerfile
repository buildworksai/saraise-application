# syntax=docker/dockerfile:1

# Multi-stage build:
# - builder installs devDependencies and builds dist/
# - runtime stage serves only dist/ (no devDependencies/node_modules)

FROM node:18.19.1-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27.4-alpine AS runtime

# SECURITY: Nginx official image runs as non-root user (nginx:nginx, UID 101)
# The nginx process runs as user 'nginx' (not root) by default in this image
# No USER directive needed - nginx image handles this automatically
# To verify: docker run --rm nginx:1.27.4-alpine id

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
