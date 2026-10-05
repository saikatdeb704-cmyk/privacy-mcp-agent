FROM python:3.11-slim as backend-builder

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Node build stage for React UI
FROM node:20-slim as frontend-builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Final Stage
FROM python:3.11-slim
WORKDIR /app
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin
COPY backend/ ./backend/
COPY --from=frontend-builder /app/dist ./dist/

# Expose port
EXPOSE 8000
ENV AGENT_HOST=0.0.0.0
ENV AGENT_PORT=8000

# Start backend
CMD ["python", "backend/main.py"]
