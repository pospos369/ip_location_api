# 基础镜像：使用Python 3.9-slim（轻量且稳定）
FROM python:3.9-slim

# 维护者信息（可选）
LABEL maintainer="IP Location API Team"
LABEL version="2.2"
LABEL description="IP地址地理位置查询接口服务（支持百度/高德/PConline等多上游自动切换）"

# 环境变量配置
# 禁止生成.pyc文件
ENV PYTHONDONTWRITEBYTECODE=1
# 实时输出日志
ENV PYTHONUNBUFFERED=1
# 时区配置
ENV TZ=Asia/Shanghai

# 设置工作目录
WORKDIR /app

# 安装系统依赖（解决requests等库的编译依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件（优先复制requirements.txt，利用Docker缓存）
COPY requirements.txt .

# 安装Python依赖（--no-cache-dir：不缓存wheel文件，减小镜像体积）
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 安全加固：创建非root用户并授权
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app \
    && chmod -R 755 /app  # 只读+执行权限，避免写入风险

# 切换到非root用户运行
USER appuser

# 暴露服务端口（与uvicorn启动端口一致）
EXPOSE 8000

# 健康检查：验证服务是否正常启动（每10秒检查一次，超时5秒，连续3次失败视为不健康）
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令（生产环境默认info日志级别，调试时可改为debug）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]