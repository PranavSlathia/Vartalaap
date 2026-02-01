# Build stage
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

# Build arguments for env vars at build time
ARG VITE_API_URL
ARG VITE_KEYCLOAK_URL
ARG VITE_KEYCLOAK_REALM
ARG VITE_KEYCLOAK_CLIENT_ID

# Build the app
RUN npm run build

# Production stage - Caddy to serve static files (consistent with tech stack)
FROM caddy:2-alpine AS production

# Copy Caddyfile
COPY Caddyfile /etc/caddy/Caddyfile

# Copy built assets
COPY --from=builder /app/dist /srv

# Expose port
EXPOSE 80

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile"]
