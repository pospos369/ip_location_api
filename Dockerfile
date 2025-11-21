# 基础镜像：Python 3.9-slim（轻量稳定，兼容所有依赖）
FROM python:3.9-slim

# 维护者与版本信息（同步项目v3.2）
LABEL maintainer="IP Location API Team"
LABEL version="3.2"
LABEL description="IP地址地理位置查询接口服务（v3.2，默认密钥优先+原生响应格式，支持百度/高德/开放平台/PConline）"

# 环境变量配置（保持与代码一致，避免硬编码）
# 禁止生成.pyc文件，减少镜像体积
ENV PYTHONDONTWRITEBYTECODE=1
# 实时输出日志，便于排查
ENV PYTHONUNBUFFERED=1
# 统一时区，与日志时间一致
ENV TZ=Asia/Shanghai
# 确保Python能正确导入项目模块
ENV PYTHONPATH=/app

# 设置工作目录
WORKDIR /app

# 安装系统依赖（仅保留必要编译依赖，适配requests等库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    curl  # 健康检查依赖（新增，确保curl可用）\
    && rm -rf /var/lib/apt/lists/*

# 优先复制依赖文件（利用Docker缓存，加速二次构建）
COPY requirements.txt .

# 安装Python依赖（严格遵循requirements.txt，无额外依赖）
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目所有代码（同步v3.2最新逻辑）
COPY . .

# 安全加固：非root用户运行（避免容器权限过高风险）
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app \
    && chmod -R 755 /app

# 切换到非root用户
USER appuser

# 暴露服务端口（与代码中uvicorn启动端口一致：8000）
EXPOSE 8000

# 健康检查（适配/v3/ip和/location/ip接口，与代码健康检查接口一致）
HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令（生产环境默认info日志，调试时可改为debug）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]