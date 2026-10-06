FROM node:22-alpine AS build
WORKDIR /lab
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY frontend/src ./frontend/src
COPY public ./public
RUN npm run build
FROM nginx:alpine
COPY --from=build /lab/dist /usr/share/nginx/html
EXPOSE 80
