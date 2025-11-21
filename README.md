# IP地址地理位置查询接口服务

![版本](https://img.shields.io/badge/version-1.0-blue.svg)
![技术栈](https://img.shields.io/badge/tech-FastAPI%20%7C%20Docker%20%7C%20Python-blue.svg)
![许可证](https://img.shields.io/badge/license-Apache%20License%202.0-blue.svg)

## 项目概述
IP Location API 是一个基于 FastAPI 构建的高性能、高可用IP地址地理位置查询后端服务。整合百度地图、高德地图、百度开放平台、PConline 四大上游数据源，支持 **自动故障转移**、**原生格式响应** 与 **统一格式转换**，同时通过严格的输入校验和容器化部署，确保生产环境的安全性与可扩展性。

### 核心价值
- 多上游冗余：避免单一接口依赖风险，提升服务可用性；
- 智能降级：AK/Key 无效/缺失时自动切换至其他上游；
- 格式兼容：支持百度/高德原生格式，同时提供统一响应格式；
- 易于部署：Docker 一键启动，支持生产环境直接使用；
- 排查便捷：完善的日志系统，支持 DEBUG 级别的数据追踪。

## 功能特性（v1.0 最新）
| 特性 | 详情 |
|------|------|
| 多上游支持 | 百度地图（需AK）、高德地图（需Key）、百度开放平台（免Key）、PConline（免Key） |
| 智能降级 | 1. 提供AK → 百度原生；2. 提供Key → 高德原生；3. 均不提供 → 用默认密钥随机选择上游 |
| 格式转换 | 非原生上游数据自动转换为目标格式（如 `/v3/ip` 始终返回高德风格格式） |
| 省份提取修复 | 支持完整提取"广东省"、"广西壮族自治区"、"北京市"等省份名称，解决部分接口省份显示不完整问题 |
| 日志排查 | 支持 INFO/DEBUG 级日志，打印上游选用、原始响应、转换结果，便于问题定位 |
| 安全加固 | IP格式严格校验（防注入）、非root用户运行、密钥脱敏、日志轮转 |
| 健康检查 | 内置健康检查接口，Docker 自动监控服务状态 |

## 快速开始

### 环境要求
- Docker 20.10+ + Docker Compose 2.0+（推荐部署方式）
- 或 Python 3.9+（手动部署）
- 百度地图 AK（可选，从 [百度地图开放平台](https://lbsyun.baidu.com/) 申请）
- 高德地图 Key（可选，从 [高德开放平台](https://lbs.amap.com/) 申请）

### 部署步骤（Docker 推荐）
1. **克隆项目**
   
   ```bash
   git clone <项目仓库地址>
   cd ip-location-api

2.**配置默认密钥**

   编辑 `docker-compose.yml`，替换以下字段为实际申请的密钥：

   ```yaml
   environment:
     - BAIDU_DEFAULT_AK=你的百度AK  # 替换为实际值
     - AMAP_DEFAULT_KEY=你的高德Key  # 替换为实际值
   ```
3. **启动服务**

   ```bash
   # 构建并后台启动
   docker-compose up -d --build
   
   # 查看启动状态
   docker-compose ps
   
   # 查看日志（验证启动成功）
   docker logs -f ip-location-api
   ```

4.**验证服务**

   服务启动后，访问 `http://localhost:8000/docs` 可查看 Swagger 接口文档，或直接用 `curl` 测试：

   ```bash
   # 测试高德风格接口（无Key，自动降级）
   curl "http://localhost:8000/v3/ip?ip=114.247.50.2"
   
   # 测试通用接口（提供百度AK，返回百度原生格式）
   curl "http://localhost:8000/location/ip?ip=114.247.50.2&ak=你的百度AK"

### 手动部署（可选）

1. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```
2. 配置环境变量（默认密钥）：

   ```bash
   # Linux/Mac
   export BAIDU_DEFAULT_AK=你的百度AK
   export AMAP_DEFAULT_KEY=你的高德Key
   
   # Windows（cmd）
   set BAIDU_DEFAULT_AK=你的百度AK
   set AMAP_DEFAULT_KEY=你的高德Key
   ```
3. 启动服务：

   ```bash
   # 生产环境
   uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
   
   # 调试模式（开启DEBUG日志）
   uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug --reload
   ```
## 接口详情

### 1. 通用 IP 查询接口
- 接口地址：`GET /location/ip`
- 功能：根据提供的密钥返回对应上游原生格式，无密钥则返回统一格式
- 请求参数：

| 参数名 | 类型   | 必选 | 说明                                       |
| ------ | ------ | ---- | ------------------------------------------ |
| ip     | string | 是   | 待查询 IPv4 地址（如 `114.247.50.2`）      |
| coor   | string | 否   | 坐标类型（仅百度地图使用，默认 `bd09ll`）  |
| ak     | string | 否   | 百度地图 AK（提供则优先调用百度原生接口）  |
| key    | string | 否   | 高德地图 Key（提供则优先调用高德原生接口） |

- 响应示例（百度原生格式）：
  ```json
  {
    "status": 0,
    "address": "CN|广东省|惠州市|None|None|100|91|89",
    "content": {
      "address": "广东省惠州市",
      "address_detail": {
        "adcode": "441300",
        "city": "惠州市",
        "city_code": 195,
        "district": "",
        "province": "广东省",
        "street": "",
        "street_number": ""
      },
      "point": {
        "x": "114.41785405731201",
        "y": "23.078590970458984"
      }
    }
  }
  ```
### 2. 高德风格 IP 查询接口

- 接口地址：`GET /v3/ip`
- 功能：始终返回高德原生格式，无 Key 时自动降级至其他上游
- 请求参数：

| 参数名 | 类型   | 必选 | 说明                                   |
| ------ | ------ | ---- | -------------------------------------- |
| ip     | string | 是   | 待查询 IPv4 地址                       |
| key    | string | 否   | 高德地图 Key（可选，不提供则自动降级） |

- 响应示例（成功，自动降级至 PConline）：

  ```json
  {
    "status": "1",
    "info": "OK（上游接口：PConline）",
    "infocode": "10000",
    "province": "广东省",
    "city": "惠州市",
    "adcode": "4400001300",
    "rectangle": ""
  }
  ```
- 响应示例（失败）：

  ```json
  {
    "status": "0",
    "info": "所有上游接口均不可用",
    "infocode": "10003",
    "province": "",
    "city": "",
    "adcode": "",
    "rectangle": ""
  }
  ```
### 3. 健康检查接口

- 接口地址：`GET /health`

- 功能：验证服务是否正常运行

- 响应：

  ```json
  {
    "status": "healthy",
    "version": "2.2",
    "timestamp": "2024-05-21T10:00:00+08:00"
  }
  ```

