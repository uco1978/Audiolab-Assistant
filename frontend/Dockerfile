FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

ARG VITE_API_BASE=https://ppc-backend-w7ey.onrender.com/api
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build

ENV PORT=5174
EXPOSE 5174

CMD ["sh", "-c", "npm run preview -- --host 0.0.0.0 --port ${PORT}"]
