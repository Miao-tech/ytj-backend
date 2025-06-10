# 使用官方Python基础镜像
FROM python:3.12.11-alpine3.21

# 设置工作目录
WORKDIR /app

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制依赖文件并安装
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

# 复制应用代码
COPY . .

# 暴露FastAPI默认端口
EXPOSE 8000

# 启动FastAPI应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
