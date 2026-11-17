# 多阶段构建：先装依赖，再拷代码
FROM python:3.12-slim AS base
WORKDIR /app

# 依赖层：pyproject 不变则命中缓存
COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv && uv pip install --system .

# 代码层
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
