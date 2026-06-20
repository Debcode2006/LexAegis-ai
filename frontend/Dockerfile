# ============================================================================
# LexAegis AI — Frontend image (Next.js 14, standalone output)
#
# Multi-stage build:
#   deps     -> install node_modules
#   builder  -> `next build` (produces .next/standalone)
#   runner   -> minimal runtime with only the standalone server + static assets
#
# NEXT_PUBLIC_* values are inlined at BUILD time, so they are passed as build
# args (see docker-compose.*.yml). Changing them requires a rebuild.
# ============================================================================

# --- Stage 1: deps ----------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# --- Stage 2: builder -------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

# Public env consumed by `next build` (baked into the client bundle).
ARG NEXT_PUBLIC_API_BASE
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# --- Stage 3: runner --------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN apk add --no-cache curl \
    && addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Standalone output bundles a minimal node_modules + server.js.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
