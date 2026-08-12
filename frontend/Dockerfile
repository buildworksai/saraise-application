# syntax=docker/dockerfile:1

# Multi-stage build:
# - builder installs devDependencies and builds dist/
# - runtime stage serves only dist/ (no devDependencies/node_modules)

FROM node:20.17.0-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --audit=false --fund=false

COPY . .
RUN npm run build

FROM nginx:1.27.4-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

USER nginx

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
