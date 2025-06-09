# 使用官方Python基础镜像
FROM python:3.12.11-alpine3.21

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露FastAPI默认端口
EXPOSE 8001

# 启动FastMCP应用
CMD ["python", "main.py"]
