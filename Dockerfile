FROM python:3.12-slim

WORKDIR /app

# 减少运行时缓存占用
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# 先装依赖（利用 Docker layer 缓存）
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# 再拷贝项目代码
COPY . /app

# 默认启动：从主目录入口启动（保证模块搜索路径稳定）
CMD ["python", "main.py"]

