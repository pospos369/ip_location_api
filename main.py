from fastapi import FastAPI, HTTPException, Query
import requests
import re
import random
import os
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timezone

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="IP Location Query API", version="3.2")

# 从环境变量读取默认密钥（避免硬编码）
BAIDU_DEFAULT_AK = os.getenv("BAIDU_DEFAULT_AK", "")
AMAP_DEFAULT_KEY = os.getenv("AMAP_DEFAULT_KEY", "")

# -------------------------- 工具函数 --------------------------
def is_valid_ip(ip: str) -> bool:
    """验证IPv4格式，防范恶意输入"""
    ip_pattern = re.compile(
        r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.)'
        r'{3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    return ip_pattern.match(ip) is not None

def extract_location_from_baidu_opendata(raw_data: Dict[str, Any]) -> Dict[str, str]:
    """从百度开放平台原生响应提取省市信息（无硬编码）"""
    location = raw_data.get("data", [{}])[0].get("location", "").strip()
    location_clean = re.sub(r'\s+[^ ]*$', '', location).strip()  # 移除运营商
    
    # 提取省份（基于省级关键词）
    province_keywords = ("省", "自治区", "直辖市", "特别行政区")
    province = ""
    remaining = location_clean
    for kw in province_keywords:
        if kw in location_clean:
            parts = location_clean.split(kw, 1)
            if len(parts) >= 2:
                province = f"{parts[0].strip()}{kw}"
                remaining = parts[1].strip()
            break
    
    # 提取城市（基于地级关键词）
    city_keywords = ("市", "州", "盟", "地区")
    city = ""
    for kw in city_keywords:
        if kw in remaining:
            parts = remaining.split(kw, 1)
            city = f"{parts[0].strip()}{kw}"
            break
    if not city and remaining:
        city = remaining.strip()
    if not city:
        city = province  # 直辖市兜底
    
    # 非直辖市校验
    is_municipality = any(kw in province for kw in ("直辖市", "特别行政区"))
    if city == province and not is_municipality:
        city_candidates = [seg.strip() for seg in remaining.split() if seg.strip()]
        city = city_candidates[0] if city_candidates else province
    
    return {"province": province.strip(), "city": city.strip(), "adcode": ""}

def extract_location_from_pconline(raw_data: Dict[str, Any]) -> Dict[str, str]:
    """从PConline原生响应提取省市信息"""
    province = raw_data.get("pro", "").strip()
    city = raw_data.get("city", "").strip()
    pro_code = str(raw_data.get("proCode", "")).strip()
    city_code = str(raw_data.get("cityCode", "")).strip()
    adcode = f"{pro_code}{city_code[2:]}" if (pro_code and city_code) else ""
    
    # 处理直辖市/缺失情况
    if not city or city == province:
        is_municipality = any(kw in province for kw in ("直辖市", "特别行政区"))
        if is_municipality:
            city = province
        else:
            city = raw_data.get("addr", "").replace(province, "").strip().split()[0]
    
    return {"province": province, "city": city, "adcode": adcode}

# -------------------------- 格式化函数（核心新增） --------------------------
def to_baidumap_format(raw_data: Dict[str, Any], ip: str, upstream: str) -> Dict[str, Any]:
    """将任意上游的原生响应转换为百度地图原生格式"""
    location_info = {"province": "", "city": "", "adcode": ""}
    
    # 按上游类型提取基础信息
    if upstream == "高德地图原生接口":
        location_info["province"] = raw_data.get("province", "").strip()
        location_info["city"] = raw_data.get("city", "").strip()
        location_info["adcode"] = raw_data.get("adcode", "").strip()
    elif upstream == "百度开放平台":
        location_info = extract_location_from_baidu_opendata(raw_data)
    elif upstream == "PConline":
        location_info = extract_location_from_pconline(raw_data)
    elif upstream == "百度地图原生接口":
        return raw_data  # 本身就是百度格式，直接返回
    
    # 构建百度原生格式
    province = location_info["province"]
    city = location_info["city"]
    adcode = location_info["adcode"]
    
    return {
        "status": 0,
        "address": f"CN|{province}|{city}||None||||",
        "content": {
            "address": f"{province}{city}",
            "address_detail": {
                "adcode": adcode,
                "city": city,
                "city_code": 0,  # 非百度接口无city_code，设为0
                "district": "",
                "province": province,
                "street": "",
                "street_number": ""
            },
            "point": {
                "x": "",  # 非百度接口无经纬度，设为空
                "y": ""
            }
        }
    }

def to_amap_format(raw_data: Dict[str, Any], ip: str, upstream: str) -> Dict[str, Any]:
    """将任意上游的原生响应转换为高德地图原生格式"""
    location_info = {"province": "", "city": "", "adcode": ""}
    
    # 按上游类型提取基础信息
    if upstream == "百度地图原生接口":
        content = raw_data.get("content", {})
        addr_detail = content.get("address_detail", {})
        location_info["province"] = addr_detail.get("province", "").strip()
        location_info["city"] = addr_detail.get("city", "").strip()
        location_info["adcode"] = addr_detail.get("adcode", "").strip()
    elif upstream == "百度开放平台":
        location_info = extract_location_from_baidu_opendata(raw_data)
    elif upstream == "PConline":
        location_info = extract_location_from_pconline(raw_data)
    elif upstream == "高德地图原生接口":
        return raw_data  # 本身就是高德格式，直接返回
    
    # 构建高德原生格式
    province = location_info["province"]
    city = location_info["city"]
    adcode = location_info["adcode"]
    
    return {
        "status": "1" if province else "0",
        "info": f"OK（上游接口：{upstream}）" if province else "未获取到地理位置信息",
        "infocode": "10000" if province else "10003",
        "province": province,
        "city": city,
        "adcode": adcode,
        "rectangle": ""  # 非高德接口无矩形范围，设为空
    }

# -------------------------- 上游原生接口调用函数 --------------------------
def query_baidu_map_native(ip: str, coor: str, ak: str) -> Optional[Dict[str, Any]]:
    """百度地图原生接口调用"""
    logger.info(f"IP:{ip} - 选用上游接口：百度地图原生接口")
    if not ak:
        logger.warning(f"IP:{ip} - 百度AK为空，跳过")
        return None
    try:
        url = "https://api.map.baidu.com/location/ip"
        params = {"ip": ip, "coor": coor, "ak": ak}
        logger.debug(f"IP:{ip} - 百度请求参数: {params}（AK脱敏）")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        raw_data = response.json()
        logger.debug(f"IP:{ip} - 百度原生响应: {raw_data}")
        return raw_data
    except Exception as e:
        logger.error(f"IP:{ip} - 百度原生接口失败: {str(e)}", exc_info=True)
        return None

def query_amap_ip_native(ip: str, key: str) -> Optional[Dict[str, Any]]:
    """高德地图原生接口调用"""
    logger.info(f"IP:{ip} - 选用上游接口：高德地图原生接口")
    if not key:
        logger.warning(f"IP:{ip} - 高德Key为空，跳过")
        return None
    try:
        url = "https://restapi.amap.com/v3/ip"
        params = {"ip": ip, "key": key}
        logger.debug(f"IP:{ip} - 高德请求参数: {params}（Key脱敏）")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        raw_data = response.json()
        logger.debug(f"IP:{ip} - 高德原生响应: {raw_data}")
        return raw_data
    except Exception as e:
        logger.error(f"IP:{ip} - 高德原生接口失败: {str(e)}", exc_info=True)
        return None

def query_baidu_opendata_native(ip: str) -> Optional[Dict[str, Any]]:
    """百度开放平台原生接口调用（新增，返回原生响应）"""
    logger.info(f"IP:{ip} - 选用上游接口：百度开放平台")
    try:
        url = "https://opendata.baidu.com/api.php"
        params = {"query": ip, "co": "", "resource_id": "6006", "oe": "utf8"}
        logger.debug(f"IP:{ip} - 百度开放平台请求参数: {params}")
        response = requests.get(url, params=params, timeout=5)
        raw_data = response.json()
        logger.debug(f"IP:{ip} - 百度开放平台原生响应: {raw_data}")
        if raw_data.get("status") == "0" and raw_data.get("data"):
            return raw_data
        logger.warning(f"IP:{ip} - 百度开放平台响应异常: {raw_data}")
        return None
    except Exception as e:
        logger.error(f"IP:{ip} - 百度开放平台接口失败: {str(e)}", exc_info=True)
        return None

def query_pconline_native(ip: str) -> Optional[Dict[str, Any]]:
    """PConline原生接口调用（新增，返回原生响应）"""
    logger.info(f"IP:{ip} - 选用上游接口：PConline")
    try:
        url = "http://whois.pconline.com.cn/ipJson.jsp"
        params = {"ip": ip, "json": "true"}
        logger.debug(f"IP:{ip} - PConline请求参数: {params}")
        response = requests.get(url, params=params, timeout=5)
        response.encoding = "gbk"
        raw_data = response.json()
        logger.debug(f"IP:{ip} - PConline原生响应: {raw_data}")
        if not raw_data.get("err"):
            return raw_data
        logger.warning(f"IP:{ip} - PConline响应错误: {raw_data.get('err')}")
        return None
    except Exception as e:
        logger.error(f"IP:{ip} - PConline接口失败: {str(e)}", exc_info=True)
        return None

# -------------------------- 接口定义 --------------------------
@app.get("/location/ip", description="通用IP查询接口（原生格式+自动转换）")
async def get_ip_location(
    ip: str = Query(..., description="待查询IPv4地址"),
    coor: str = Query("bd09ll", description="坐标类型（仅百度地图使用）"),
    ak: Optional[str] = Query(None, description="百度地图AK（优先级最高，返回百度原生格式）"),
    key: Optional[str] = Query(None, description="高德地图Key（优先级次高，返回高德原生格式）")
) -> Dict[str, Any]:
    """
    核心逻辑（与原有一致）：
    1. 提供ak → 百度原生格式
    2. 不提供 → 先尝试默认密钥上游（优先级高），再尝试免密钥上游
    """
    logger.info(f"IP:{ip} - 收到通用查询请求，ak={'提供' if ak else '未提供'}，key={'提供' if key else '未提供'}")
    
    # IP校验
    if not is_valid_ip(ip):
        logger.warning(f"IP:{ip} - 无效IPv4格式")
        raise HTTPException(status_code=400, detail="无效的IPv4地址格式")
    
    # 1. 提供ak → 百度原生
    if ak:
        result = query_baidu_map_native(ip, coor, ak)
        if result:
            logger.info(f"IP:{ip} - 百度原生接口返回成功")
            return result
        raise HTTPException(status_code=503, detail="百度地图接口调用失败（AK无效/网络异常）")
    
    # 2. 无密钥 → 优先级：默认密钥上游（第一优先级）> 免密钥上游（第二优先级）
    # 第一优先级：默认密钥对应的上游（优先级高）
    first_priority = []
    if BAIDU_DEFAULT_AK:
        first_priority.append(("百度地图原生接口", lambda: query_baidu_map_native(ip, coor, BAIDU_DEFAULT_AK)))
    if AMAP_DEFAULT_KEY:
        first_priority.append(("高德地图原生接口", lambda: query_amap_ip_native(ip, AMAP_DEFAULT_KEY)))
    
    # 第二优先级：免密钥上游（优先级低）
    second_priority = [
        ("百度开放平台", lambda: query_baidu_opendata_native(ip)),
        ("PConline", lambda: query_pconline_native(ip))
    ]
    
    # 合并所有上游（第一优先级在前，第二优先级在后）
    all_upstreams = first_priority.copy()
    all_upstreams.extend(second_priority)
    
    if not all_upstreams:
        raise HTTPException(status_code=500, detail="未配置默认密钥，且无可用免密钥上游")
    
    # 随机选择目标格式（百度/高德）
    target_format = random.choice(["baidu", "amap"])
    logger.info(f"IP:{ip} - 无密钥，上游顺序（第一优先级→第二优先级）: {[name for name, _ in all_upstreams]}, 目标格式: {target_format}")
    
    # 按顺序尝试所有上游（先第一优先级，再第二优先级）
    for name, func in all_upstreams:
        logger.info(f"IP:{ip} - 尝试上游：{name}")
        raw_result = func()
        if raw_result:
            if target_format == "baidu":
                formatted_result = to_baidumap_format(raw_result, ip, name)
                logger.info(f"IP:{ip} - 转换为百度格式成功")
                return formatted_result
            else:
                formatted_result = to_amap_format(raw_result, ip, name)
                logger.info(f"IP:{ip} - 转换为高德格式成功")
                return formatted_result
    
    raise HTTPException(status_code=503, detail="所有上游接口均不可用，请稍后再试")

@app.get("/v3/ip", description="高德地图风格IP查询接口（始终返回高德原生格式）")
async def amap_style_ip_query(
    ip: str = Query(..., description="待查询IPv4地址"),
    key: Optional[str] = Query(None, description="高德地图Key（可选，不提供则自动降级）")
) -> Dict[str, Any]:
    """
    逻辑（与原有一致）：
    1. 提供key → 高德原生格式
    2. 不提供key → 先尝试默认密钥上游（优先级高），再尝试免密钥上游
    """
    logger.info(f"IP:{ip} - 收到高德风格查询请求，key={'提供' if key else '未提供'}")
    
    # IP校验
    if not is_valid_ip(ip):
        logger.warning(f"IP:{ip} - 无效IPv4格式")
        return {
            "status": "0",
            "info": "无效的IPv4地址格式",
            "infocode": "10001",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": ""
        }
    
    # 1. 提供key → 高德原生
    if key:
        result = query_amap_ip_native(ip, key)
        if result:
            logger.info(f"IP:{ip} - 高德原生接口返回成功")
            return result
        logger.warning(f"IP:{ip} - 高德原生接口失败，自动降级")
    
    # 2. 降级 → 优先级：默认密钥上游（第一优先级）> 免密钥上游（第二优先级）
    # 第一优先级：默认密钥对应的上游（优先级高）
    first_priority = []
    if AMAP_DEFAULT_KEY:
        first_priority.append(("高德地图原生接口", lambda: query_amap_ip_native(ip, AMAP_DEFAULT_KEY)))
    if BAIDU_DEFAULT_AK:
        first_priority.append(("百度地图原生接口", lambda: query_baidu_map_native(ip, "bd09ll", BAIDU_DEFAULT_AK)))
    
    # 第二优先级：免密钥上游（优先级低）
    second_priority = [
        ("百度开放平台", lambda: query_baidu_opendata_native(ip)),
        ("PConline", lambda: query_pconline_native(ip))
    ]
    
    # 合并所有上游（第一优先级在前，第二优先级在后）
    all_upstreams = first_priority.copy()
    all_upstreams.extend(second_priority)
    
    if not all_upstreams:
        logger.error(f"IP:{ip} - 无可用降级上游")
        return {
            "status": "0",
            "info": "无可用上游接口（未配置默认密钥）",
            "infocode": "10002",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": ""
        }
    
    logger.info(f"IP:{ip} - 降级上游顺序（第一优先级→第二优先级）: {[name for name, _ in all_upstreams]}")
    
    # 按顺序尝试所有上游（先第一优先级，再第二优先级）
    for name, func in all_upstreams:
        logger.info(f"IP:{ip} - 尝试降级上游：{name}")
        raw_result = func()
        if raw_result:
            formatted_result = to_amap_format(raw_result, ip, name)
            logger.info(f"IP:{ip} - 降级转换为高德格式成功")
            return formatted_result
    
    # 所有上游失败
    logger.error(f"IP:{ip} - 所有降级上游均失败")
    return {
        "status": "0",
        "info": "所有上游接口均不可用",
        "infocode": "10003",
        "province": "",
        "city": "",
        "adcode": "",
        "rectangle": ""
    }

@app.get("/health", description="服务健康检查接口")
async def health_check() -> Dict[str, str]:
    """健康检查接口（Docker监控用）"""
    tz = timezone.utc
    local_time = datetime.now(tz).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    return {
        "status": "healthy",
        "version": "3.2",
        "timestamp": local_time
    }

if __name__ == "__main__":
    import uvicorn
    # 生产环境用info级别，调试时改为debug
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")