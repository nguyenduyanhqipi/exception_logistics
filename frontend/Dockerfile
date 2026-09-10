FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

# Key Tilemap của VietMap phải có LÚC BUILD: Vite bake mọi biến VITE_* vào
# bundle, không đọc được lúc chạy — thiếu arg này thì bản deploy ra bản đồ
# trắng trơn mà không có lỗi nào trong log.
ARG VITE_VIETMAP_TILEMAP_KEY
ENV VITE_VIETMAP_TILEMAP_KEY=${VITE_VIETMAP_TILEMAP_KEY}

RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
