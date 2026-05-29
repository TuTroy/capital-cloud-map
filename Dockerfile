FROM python:3.11-slim

WORKDIR /app

# 安装依赖（复用缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝源码
COPY . .

# 运行时
EXPOSE 8080
ENV FLASK_HOST=0.0.0.0
CMD ["python", "app.py"]
