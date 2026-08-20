FROM node:20-alpine AS frontend

WORKDIR /opt/rec-console/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /opt/rec-console
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
COPY rec_console ./rec_console
COPY --from=frontend /opt/rec-console/frontend/dist ./rec_console/static

EXPOSE 8095
CMD ["uvicorn", "rec_console.main:app", "--host", "0.0.0.0", "--port", "8095"]
