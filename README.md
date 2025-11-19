# IP地址地理位置查询接口服务

一个高性能、高可用的IP地址地理位置查询后端接口，基于FastAPI构建，整合多上游数据源，支持自动故障转移与容器化部署。


## 功能特点

1. **多上游数据源**：整合百度地图、百度开放平台、PConline等多个IP查询接口，自动切换确保可用性；  
2. **智能故障转移**：当百度地图AK无效、缺失或受限（如错误码240/230/101）时，自动切换至其他上游接口；  
3. **严格数据校验**：强制验证IP格式，防范SQL注入等恶意输入；确保响应中`省份`和`城市`信息必填；  
4. **统一响应格式**：输出格式标准化，与百度地图接口响应结构兼容；  
5. **容器化部署**：提供Docker配置，支持快速部署与扩展。  


## 响应格式示例

```json
{
  "status": 0,
  "address": "CN|广东省|清远市|清新区|None|100|91|89",
  "content": {
    "address": "广东省清远市清新区",
    "address_detail": {
      "adcode": "441803",
      "city": "清远市",
      "city_code": 197,
      "district": "清新区",
      "province": "广东省",
      "street": "",
      "street_number": ""
    },
    "point": {
      "x": "113.02403576132977",
      "y": "23.74023614897897"
    }
  }
}

字段说明：
- `status`：状态码（0 = 成功，非 0 = 失败）；
- `address`：地址层级串（格式：国家 | 省份 | 城市 | 区县 |...）；
- `content.address_detail`：详细地址信息（`province`和`city`为必填项）；
- `content.point`：经纬度坐标（仅百度地图接口返回，其他接口可能为空）。
```

## 快速开始

### 环境要求

- 推荐：Docker 20.10+ 与 Docker Compose 2.0+
- 手动部署：Python 3.9+

### 项目结构

```plaintext
ip_location_api/
├── main.py           # 核心逻辑（接口定义、上游调用、数据转换）
├── Dockerfile        # Docker构建配置
├── docker-compose.yml # 容器编排配置
└── requirements.txt  # 依赖清单
```

### 部署方式

#### 方式 1：Docker 部署（推荐）

1. **克隆项目**

   ```bash
   git clone <项目仓库地址>
   cd ip_location_api

2. **启动服务**

   一键构建并启动容器（默认端口 8000）：

   ```bash
   docker-compose up -d --build
   ```
3. **验证部署**

   服务启动后，通过`curl`或浏览器访问接口：

   ```bash
   # 无AK调用（自动使用百度开放平台/PConline）
   curl "http://localhost:8000/location/ip?ip=1.1.1.1"
   
   # 有AK调用（优先使用百度地图）
   curl "http://localhost:8000/location/ip?ip=1.1.1.1&ak=你的百度AK"
   ```

   若返回上述示例格式的 JSON，说明部署成功。

#### 方式 2：手动部署

1. **安装依赖**

   ```bash
   pip install -r requirements.txt
   ```
2. **启动服务**

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

   （`--reload`为开发模式热重载，生产环境建议移除）

### 接口说明

#### 接口地址

```
GET /location/ip
```

#### 请求参数

| 参数名 | 类型   | 是否必选 | 说明                                          |
| ------ | ------ | -------- | --------------------------------------------- |
| ip     | string | 是       | 待查询的 IPv4 地址（如`1.1.1.1`）             |
| coor   | string | 否       | 坐标类型（默认`bd09ll`，仅百度地图接口使用）  |
| ak     | string | 否       | 百度地图 AK（可选，不提供则跳过百度地图接口） |

#### 上游接口切换逻辑

服务按以下优先级调用上游接口，返回第一个有效结果：

1. 若提供`ak`，优先调用**百度地图接口**；
2. 若百度地图接口失败（AK 无效 / 超时 / 数据缺失），切换至**百度开放平台接口**；
3. 若百度开放平台接口失败，切换至**PConline 接口**；
4. 所有接口失败时，返回`503 Service Unavailable`。

## 安全与性能优化

1. **输入安全**
   - 基于正则表达式严格校验 IP 格式（`xxx.xxx.xxx.xxx`，每个段 0-255），拒绝包含特殊字符的恶意输入；
   - 上游接口调用设置 5 秒超时，避免因外部服务异常导致本服务阻塞。
2. **性能建议**
   - 高并发场景建议在前端添加缓存层（如 Redis），缓存 IP 查询结果（缓存时效可设为 1-24 小时）；
   - 生产环境部署时，通过`docker-compose`扩展容器实例数量，配合 Nginx 负载均衡。

## 扩展与定制

### 新增上游接口

1. 在`main.py`中实现新接口的查询函数（参考`query_baidu_opendata`或`query_pconline`），返回`IPResponse`对象；
2. 在`get_ip_location`函数的`upstream_apis`列表中添加新函数，调整调用优先级。

### 配置调整

- 端口修改：在`docker-compose.yml`中修改`ports`映射（如`"80:8000"`）；
- 日志级别：在`main.py`中调整`logging.basicConfig(level=logging.INFO)`（可选`DEBUG`/`WARNING`）；
- 超时时间：修改上游接口调用的`timeout`参数（默认 5 秒）。

## 常见问题

1. **为什么返回`503`错误？**

   可能是所有上游接口均不可用（如网络问题、接口变更），可查看容器日志（`docker logs ip-location-api_ip-location-api_1`）排查具体错误。

2. **百度 AK 如何获取？**

   需在[百度地图开放平台](https://lbsyun.baidu.com/)注册账号，创建应用后获取 AK（选择 “IP 定位” 服务）。

3. **是否支持 IPv6？**

   目前仅支持 IPv4，如需 IPv6 可扩展`is_valid_ip`函数的正则表达式，并确认上游接口是否支持。
