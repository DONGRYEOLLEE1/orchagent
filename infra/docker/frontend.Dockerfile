# Use Node.js for building
FROM node:20-slim AS builder

WORKDIR /app

# Copy package files
COPY apps/frontend/package*.json ./apps/frontend/
WORKDIR /app/apps/frontend
RUN npm install

# Copy source and build
COPY apps/frontend .
RUN npm run build

# --- Runner Stage ---
FROM node:20-slim

WORKDIR /app/apps/frontend

# Copy built files
COPY --from=builder /app/apps/frontend/package*.json ./
COPY --from=builder /app/apps/frontend/.next ./.next
COPY --from=builder /app/apps/frontend/public ./public
COPY --from=builder /app/apps/frontend/node_modules ./node_modules

# Set environment variables
ENV NODE_ENV=production

# Command to run the frontend
EXPOSE 3000
CMD ["npm", "start"]
