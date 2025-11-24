# IP地址地理位置查询接口服务
![版本](https://img.shields.io/badge/version-1.0-blue.svg)
![技术栈](https://img.shields.io/badge/tech-FastAPI%20%7C%20Docker%20%7C%20Python-blue.svg)
![许可证](https://img.shields.io/badge/license-Apache%20License%202.0-blue.svg)

# 项目简介

本项目是基于FastAPI开发的IP地址地理位置查询接口服务，核心能力是通过调用百度、高德地图等上游接口，返回符合官方规范的原生格式响应，并支持上游节点的精细化控制（启用/禁用），解决IP定位场景中接口兼容性、可用性问题。

当前稳定版本：v3.0 | 最后更新时间：2025-11-26

# 核心功能

- **明确原生接口定义**：严格区分「原生上游」与「非原生上游」，仅对应接口的目标地图接口可返回原生响应（如`/location/ip`仅百度地图IP接口为原生上游）。

- **上游节点开关控制**：支持通过环境变量独立控制每个上游接口的参与状态，灵活适配业务需求（如禁用不稳定的上游）。

- **严格格式转换**：非原生上游的响应会强制转换为目标接口的原生格式（如`/location/ip`固定返回百度原生格式），避免格式混乱。

- **优先级调度逻辑**：默认密钥上游（百度/高德原生接口）优先级高于免密钥上游（百度开放平台、PConline），确保响应稳定性。

- **健康检查机制**：提供`/health`接口实时反馈服务状态及上游开关配置，便于监控。

- **安全部署**：基于Docker容器化部署，非root用户运行，减少权限风险，支持日志轮转避免磁盘占用过高。

# 版本更新日志

|版本号|更新日期|核心更新|
|---|---|---|
|v3.5|2025-11-26|修复`/location/ip`格式混乱问题，强制该接口固定返回百度原生格式；<br>优化日志输出，明确格式转换过程。<br>强化格式转换逻辑，确保非原生上游必转换。<br>新增上游节点开关控制功能，支持通过环境变量启用/禁用单个上游接口；健康检查接口返回开关状态。<br>拆分上游优先级（默认密钥上游>免密钥上游），按顺序尝试调用；优化Docker部署配置。|

# 环境依赖

- 系统依赖：Docker 20.10+、Docker Compose 3.8+

- Python依赖：见`requirements.txt`（FastAPI、requests、uvicorn等）

- 第三方依赖：百度地图AK、高德地图Key（可选，优先使用带密钥接口）

# 快速部署

## 1. 环境准备

1.1 安装Docker和Docker Compose（参考[官方文档](https://docs.docker.com/get-docker/)）；

1.2 申请第三方密钥（可选但推荐）：

- 百度地图AK：前往[百度地图开放平台](https://lbsyun.baidu.com/)申请（功能：IP定位）；

- 高德地图Key：前往[高德地图开放平台](https://lbs.amap.com/)申请（功能：IP定位）。

## 2. 配置项目

克隆项目代码后，修改`docker-compose.yml`中的环境变量配置（核心配置如下）：

```yaml
environment:
  # 基础配置
  - TZ=Asia/Shanghai
  # 密钥配置（必填，优先使用带密钥接口）
  - BAIDU_DEFAULT_AK=你的百度地图AK
  - AMAP_DEFAULT_KEY=你的高德地图Key
  # 上游开关配置（可选，默认全部启用，值为true/false）
  - ENABLE_BAIDU_MAP_IP=true  # 百度地图IP原生接口
  - ENABLE_AMAP_IP=true       # 高德地图IP原生接口
  - ENABLE_BAIDU_OPENDATA=true# 百度开放平台（免密钥）
  - ENABLE_PCONLINE=true      # PConline（免密钥）
```

## 3. 构建与启动

在项目根目录执行以下命令，自动构建镜像并启动服务：

```bash
# 构建镜像并后台启动服务
docker-compose up -d --build

# 查看服务状态（确保状态为healthy）
docker-compose ps

# 查看实时日志
docker logs -f ip-location-api-v3.5
```

## 4. 验证部署

服务启动后，访问健康检查接口验证可用性：

```bash
curl http://localhost:8000/health
```

成功响应示例（含服务状态和上游开关）：

```json
{
  "status": "healthy",
  "version": "3.5",
  "timestamp": "2025-11-26T10:30:00+0800",
  "upstream_switches": "{'baidu_map_ip': True, 'amap_ip': True, 'baidu_opendata': True, 'pconline': True}"
}
```

# 接口使用说明

服务默认端口为8000，支持两个核心接口，均返回对应地图的原生格式响应。

## 1. 通用IP查询接口（百度原生格式）

**接口地址**：`GET /location/ip`

**功能描述**：固定返回百度地图IP定位原生格式，优先使用百度/高德带密钥接口，支持自动降级。

### 请求参数

|参数名|类型|是否必填|描述|
|---|---|---|---|
|ip|string|是|待查询的IPv4地址（如123.64.253.93）|
|ak|string|否|百度地图AK（优先级最高，直接调用百度原生接口）|
|key|string|否|高德地图Key（优先级次高，调用后转换为百度格式）|
|coor|string|否|百度坐标类型（默认bd09ll，仅百度接口使用）|
### 响应格式（百度原生）

```json
{
  "status": 0,          // 0表示成功，非0表示失败
  "message": "success", // 状态描述
  "address": "CN|广东省|惠州市||None||||", // 简化地址信息
  "content": {
    "address": "广东省惠州市", // 完整地址
    "address_detail": {
      "adcode": "441300",     // 行政区划代码
      "city": "惠州市",       // 城市
      "city_code": 0,         // 城市编码（非百度接口返回0）
      "district": "",         // 区县（无数据时为空）
      "province": "广东省",   // 省份
      "street": "",           // 街道（无数据时为空）
      "street_number": ""     // 门牌号（无数据时为空）
    },
    "point": { "x": "", "y": "" } // 经纬度（非百度接口返回空）
  }
}
```

### 调用示例

```bash
# 1. 提供百度AK（返回百度原生响应）
curl "http://localhost:8000/location/ip?ip=123.64.253.93&ak=你的百度AK"

# 2. 提供高德Key（转换为百度格式）
curl "http://localhost:8000/location/ip?ip=123.64.253.93&key=你的高德Key"

# 3. 无密钥（自动使用默认密钥/免密钥上游，转换为百度格式）
curl "http://localhost:8000/location/ip?ip=123.64.253.93"
```

## 2. 高德风格IP查询接口（高德原生格式）

**接口地址**：`GET /v3/ip`

**功能描述**：固定返回高德地图IP定位原生格式，兼容高德官方接口规范。

### 请求参数

|参数名|类型|是否必填|描述|
|---|---|---|---|
|ip|string|是|待查询的IPv4地址|
|key|string|否|高德地图Key（提供则直接调用高德原生接口）|
### 响应格式（高德原生）

```json
{
  "status": "1",                // 1表示成功，0表示失败
  "info": "OK（上游接口：高德地图IP原生接口）", // 状态描述
  "infocode": "10000",          // 10000表示成功，其他为错误码
  "province": "广东省",          // 省份
  "city": "惠州市",              // 城市
  "adcode": "441300",           // 行政区划代码
  "rectangle": ""               // 矩形范围（非高德接口返回空）
}
```

### 调用示例

```bash
# 1. 提供高德Key（返回高德原生响应）
curl "http://localhost:8000/v3/ip?ip=123.64.253.93&key=你的高德Key"

# 2. 无密钥（自动降级，转换为高德格式）
curl "http://localhost:8000/v3/ip?ip=123.64.253.93"
```

# 上游节点控制

通过环境变量开关控制上游接口是否参与竞选，核心规则：

- 开关默认值为`true`（全部启用），设置为`false`则禁用对应上游；

- 用户主动提供`ak`/`key`时，不受开关控制（强制调用对应接口）；

- 上游优先级：默认密钥上游（百度/高德）> 免密钥上游（百度开放平台>PConline）。

开关与上游接口的对应关系：

|环境变量|对应上游接口|类型|
|---|---|---|
|ENABLE_BAIDU_MAP_IP|百度地图IP接口（https://api.map.baidu.com/location/ip）|密钥上游|
|ENABLE_AMAP_IP|高德地图IP接口（https://restapi.amap.com/v3/ip）|密钥上游|
|ENABLE_BAIDU_OPENDATA|百度开放平台接口（https://opendata.baidu.com/api.php）|免密钥上游|
|ENABLE_PCONLINE|PConline接口（http://whois.pconline.com.cn/ipJson.jsp）|免密钥上游|
# 常见问题

## Q1：接口返回「无效的IPv4地址格式」？

A1：请检查请求的`ip`参数是否为合法IPv4地址（如192.168.1.1），不支持IPv6或域名。

## Q2：提供密钥后接口仍调用失败？

A2：请确认：1. 密钥未过期且已启用「IP定位」功能；2. 服务器IP在密钥的白名单内（若配置了白名单）。

## Q3：如何禁用所有免密钥上游？

A3：在`docker-compose.yml`中设置`ENABLE_BAIDU_OPENDATA=false`和`ENABLE_PCONLINE=false`，重启服务即可。

## Q4：健康检查显示「unhealthy」？

A4：执行`docker logs ip-location-api-v3.5`查看日志，排查服务启动失败原因（如端口占用、密钥配置错误）。

# 维护信息

项目维护：IP Location API Team

版本迭代：基于用户反馈持续优化，核心变更记录见「版本更新日志」

问题反馈：建议通过日志定位问题后，提供接口调用参数、日志信息进行反馈