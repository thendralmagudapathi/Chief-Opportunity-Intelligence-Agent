# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app


FROM base AS deps
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install


FROM deps AS development
COPY frontend .
EXPOSE 3000
CMD ["npm", "run", "dev"]


FROM deps AS builder
COPY frontend .
RUN npm run build


FROM base AS runtime
ENV NODE_ENV=production
RUN addgroup -g 10001 nodejs && adduser -u 10001 -G nodejs -S nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
