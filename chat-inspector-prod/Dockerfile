FROM node:20-alpine

WORKDIR /app

# 安装dumb-init来处理信号
RUN apk add --no-cache dumb-init curl

# 创建非root用户
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# 复制package文件并安装依赖
COPY --chown=nodejs:nodejs package*.json ./
COPY --chown=nodejs:nodejs client/package*.json ./client/
COPY --chown=nodejs:nodejs server/package*.json ./server/

RUN npm ci --only=production

# 复制构建产物
COPY --chown=nodejs:nodejs client/dist ./client/dist
COPY --chown=nodejs:nodejs client/bin ./client/bin
COPY --chown=nodejs:nodejs server/build ./server/build

# 切换到非root用户
USER nodejs

# 暴露端口
EXPOSE 6274 6277

# 设置环境变量
ENV NODE_ENV=production
ENV CLIENT_PORT=6274
ENV SERVER_PORT=6277

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:6274 || exit 1

# 使用dumb-init启动应用
ENTRYPOINT ["dumb-init", "--"]
CMD ["npm", "start"] 