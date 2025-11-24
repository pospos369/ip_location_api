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

app = FastAPI(title="IP Location Query API", version="3.5")

# -------------------------- 核心配置（无变更） --------------------------
def get_env_boolean(key: str, default: bool = True) -> bool:
    value = os.getenv(key, str(default)).strip().lower()
    return value in ("true", "1", "yes")

UPSTREAM_SWITCHES = {
    "baidu_map_ip": get_env_boolean("ENABLE_BAIDU_MAP_IP"),
    "amap_ip": get_env_boolean("ENABLE_AMAP_IP"),
    "baidu_opendata": get_env_boolean("ENABLE_BAIDU_OPENDATA"),
    "pconline": get_env_boolean("ENABLE_PCONLINE")
}

BAIDU_DEFAULT_AK = os.getenv("BAIDU_DEFAULT_AK", "")
AMAP_DEFAULT_KEY = os.getenv("AMAP_DEFAULT_KEY", "")

# -------------------------- 工具函数（无变更） --------------------------
def is_valid_ip(ip: str) -> bool:
    ip_pattern = re.compile(
        r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.)'
        r'{3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    return ip_pattern.match(ip) is not None

def extract_location_from_baidu_opendata(raw_data: Dict[str, Any]) -> Dict[str, str]:
    location = raw_data.get("data", [{}])[0].get("location", "").strip()
    location_clean = re.sub(r'\s+[^ ]*$', '', location).strip()
    
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
        city = province
    
    is_municipality = any(kw in province for kw in ("直辖市", "特别行政区"))
    if city == province and not is_municipality:
        city_candidates = [seg.strip() for seg in remaining.split() if seg.strip()]
        city = city_candidates[0] if city_candidates else province
    
    return {"province": province.strip(), "city": city.strip(), "adcode": ""}

def extract_location_from_pconline(raw_data: Dict[str, Any]) -> Dict[str, str]:
    province = raw_data.get("pro", "").strip()
    city = raw_data.get("city", "").strip()
    pro_code = str(raw_data.get("proCode", "")).strip()
    city_code = str(raw_data.get("cityCode", "")).strip()
    adcode = f"{pro_code}{city_code[2:]}" if (pro_code and city_code) else ""
    
    if not city or city == province:
        is_municipality = any(kw in province for kw in ("直辖市", "特别行政区"))
        if is_municipality:
            city = province
        else:
            city = raw_data.get("addr", "").replace(province, "").strip().split()[0]
    
    return {"province": province, "city": city, "adcode": adcode}

# -------------------------- 格式化函数（无变更，确保仅百度格式输出） --------------------------
def to_baidumap_format(raw_data: Dict[str, Any], ip: str, upstream: str) -> Dict[str, Any]:
    logger.debug(f"IP:{ip} - 开始转换为百度格式，上游：{upstream}，原始响应：{raw_data}")
    location_info = {"province": "", "city": "", "adcode": ""}
    
    if upstream == "高德地图IP接口":
        location_info["province"] = raw_data.get("province", "").strip()
        location_info["city"] = raw_data.get("city", "").strip()
        location_info["adcode"] = raw_data.get("adcode", "").strip()
        logger.debug(f"IP:{ip} - 从高德IP接口提取信息：{location_info}")
    elif upstream == "百度开放平台":
        location_info = extract_location_from_baidu_opendata(raw_data)
    elif upstream == "PConline":
        location_info = extract_location_from_pconline(raw_data)
    elif upstream == "百度地图IP接口":
        logger.debug(f"IP:{ip} - 上游为百度IP接口，直接返回响应")
        return raw_data
    
    province = location_info["province"]
    city = location_info["city"]
    adcode = location_info["adcode"]
    
    formatted_result = {
        "status": 0,
        "message": "success",
        "address": f"CN|{province}|{city}||None||||",
        "content": {
            "address": f"{province}{city}" if (province and city) else "",
            "address_detail": {
                "adcode": adcode,
                "city": city,
                "city_code": 0,
                "district": "",
                "province": province,
                "street": "",
                "street_number": ""
            },
            "point": {"x": "", "y": ""}
        }
    }
    logger.debug(f"IP:{ip} - 百度格式转换完成：{formatted_result}")
    return formatted_result

def to_amap_format(raw_data: Dict[str, Any], ip: str, upstream: str) -> Dict[str, Any]:
    logger.debug(f"IP:{ip} - 开始转换为高德格式，上游：{upstream}，原始响应：{raw_data}")
    location_info = {"province": "", "city": "", "adcode": ""}
    
    if upstream == "百度地图IP接口":
        content = raw_data.get("content", {})
        addr_detail = content.get("address_detail", {})
        location_info["province"] = addr_detail.get("province", "").strip()
        location_info["city"] = addr_detail.get("city", "").strip()
        location_info["adcode"] = addr_detail.get("adcode", "").strip()
        logger.debug(f"IP:{ip} - 从百度IP接口提取信息：{location_info}")
    elif upstream == "百度开放平台":
        location_info = extract_location_from_baidu_opendata(raw_data)
    elif upstream == "PConline":
        location_info = extract_location_from_pconline(raw_data)
    elif upstream == "高德地图IP接口":
        logger.debug(f"IP:{ip} - 上游为高德IP接口，直接返回响应")
        return raw_data
    
    province = location_info["province"]
    city = location_info["city"]
    adcode = location_info["adcode"]
    
    formatted_result = {
        "status": "1" if province else "0",
        "info": "OK" if province else "未获取到地理位置信息",
        "infocode": "10000" if province else "10003",
        "province": province,
        "city": city,
        "adcode": adcode,
        "rectangle": ""
    }
    logger.debug(f"IP:{ip} - 高德格式转换完成：{formatted_result}")
    return formatted_result

# -------------------------- 上游接口调用函数（无变更） --------------------------
def query_baidu_map_ip_native(ip: str, coor: str, ak: str) -> Optional[Dict[str, Any]]:
    upstream_name = "百度地图IP接口"
    logger.info(f"IP:{ip} - 选用上游接口：{upstream_name}")
    if not ak:
        logger.warning(f"IP:{ip} - 百度AK为空，跳过{upstream_name}")
        return None
    try:
        url = "https://api.map.baidu.com/location/ip"
        params = {"ip": ip, "coor": coor, "ak": ak}
        logger.debug(f"IP:{ip} - {upstream_name}请求参数: {params}（AK脱敏）")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        raw_data = response.json()
        logger.debug(f"IP:{ip} - {upstream_name}响应: {raw_data}")
        return raw_data
    except Exception as e:
        logger.error(f"IP:{ip} - {upstream_name}调用失败: {str(e)}", exc_info=True)
        return None

def query_amap_ip_native(ip: str, key: str) -> Optional[Dict[str, Any]]:
    upstream_name = "高德地图IP接口"
    logger.info(f"IP:{ip} - 选用上游接口：{upstream_name}")
    if not key:
        logger.warning(f"IP:{ip} - 高德Key为空，跳过{upstream_name}")
        return None
    try:
        url = "https://restapi.amap.com/v3/ip"
        params = {"ip": ip, "key": key}
        logger.debug(f"IP:{ip} - {upstream_name}请求参数: {params}（Key脱敏）")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        raw_data = response.json()
        logger.debug(f"IP:{ip} - {upstream_name}响应: {raw_data}")
        return raw_data
    except Exception as e:
        logger.error(f"IP:{ip} - {upstream_name}调用失败: {str(e)}", exc_info=True)
        return None

def query_baidu_opendata_native(ip: str) -> Optional[Dict[str, Any]]:
    upstream_name = "百度开放平台"
    logger.info(f"IP:{ip} - 选用上游接口：{upstream_name}")
    try:
        url = "https://opendata.baidu.com/api.php"
        params = {"query": ip, "co": "", "resource_id": "6006", "oe": "utf8"}
        logger.debug(f"IP:{ip} - {upstream_name}请求参数: {params}")
        response = requests.get(url, params=params, timeout=5)
        raw_data = response.json()
        logger.debug(f"IP:{ip} - {upstream_name}响应: {raw_data}")
        if raw_data.get("status") == "0" and raw_data.get("data"):
            return raw_data
        logger.warning(f"IP:{ip} - {upstream_name}响应异常: {raw_data}")
        return None
    except Exception as e:
        logger.error(f"IP:{ip} - {upstream_name}调用失败: {str(e)}", exc_info=True)
        return None

def query_pconline_native(ip: str) -> Optional[Dict[str, Any]]:
    upstream_name = "PConline"
    logger.info(f"IP:{ip} - 选用上游接口：{upstream_name}")
    try:
        url = "http://whois.pconline.com.cn/ipJson.jsp"
        params = {"ip": ip, "json": "true"}
        logger.debug(f"IP:{ip} - {upstream_name}请求参数: {params}")
        response = requests.get(url, params=params, timeout=5)
        response.encoding = "gbk"
        raw_data = response.json()
        logger.debug(f"IP:{ip} - {upstream_name}响应: {raw_data}")
        if not raw_data.get("err"):
            return raw_data
        logger.warning(f"IP:{ip} - {upstream_name}响应错误: {raw_data.get('err')}")
        return None
    except Exception as e:
        logger.error(f"IP:{ip} - {upstream_name}调用失败: {str(e)}", exc_info=True)
        return None

# -------------------------- 接口定义（核心修正：/location/ip强制百度格式） --------------------------
@app.get("/location/ip", description="通用IP查询接口（固定目标格式：百度，仅百度IP接口为上游）")
async def get_ip_location(
    ip: str = Query(..., description="待查询IPv4地址"),
    coor: str = Query("bd09ll", description="坐标类型（仅百度IP接口使用）"),
    ak: Optional[str] = Query(None, description="百度地图AK（优先级最高，调用百度IP接口）"),
    key: Optional[str] = Query(None, description="高德地图Key（优先级次高，调用高德IP接口后转换为百度格式）")
) -> Dict[str, Any]:
    logger.info(f"IP:{ip} - 收到通用查询请求，ak={'提供' if ak else '未提供'}，key={'提供' if key else '未提供'}")
    
    if not is_valid_ip(ip):
        logger.warning(f"IP:{ip} - 无效IPv4格式")
        raise HTTPException(status_code=400, detail="无效的IPv4地址格式")
    
    # 1. 提供ak → 百度IP接口（返回百度响应）
    if ak:
        result = query_baidu_map_ip_native(ip, coor, ak)
        if result:
            logger.info(f"IP:{ip} - 百度IP接口返回成功（百度格式）")
            return result
        raise HTTPException(status_code=503, detail="百度地图IP接口调用失败（AK无效/网络异常）")
    
    # 2. 提供key → 高德IP接口（转换为百度格式）
    if key:
        logger.info(f"IP:{ip} - 提供高德Key，调用高德IP接口后强制转换为百度格式")
        raw_result = query_amap_ip_native(ip, key)
        if raw_result:
            formatted_result = to_baidumap_format(raw_result, ip, "高德地图IP接口")
            logger.info(f"IP:{ip} - 高德IP接口响应转换为百度格式成功")
            return formatted_result
        raise HTTPException(status_code=503, detail="高德地图IP接口调用失败（Key无效/网络异常）")
    
    # 3. 无密钥 → 按优先级尝试上游，所有非上游均强制转换为百度格式（核心修正：移除随机格式）
    logger.info(f"IP:{ip} - 无密钥，上游开关状态: {UPSTREAM_SWITCHES}")
    
    first_priority = []
    if BAIDU_DEFAULT_AK and UPSTREAM_SWITCHES["baidu_map_ip"]:
        first_priority.append(("百度地图IP接口", lambda: query_baidu_map_ip_native(ip, coor, BAIDU_DEFAULT_AK)))
    if AMAP_DEFAULT_KEY and UPSTREAM_SWITCHES["amap_ip"]:
        first_priority.append(("高德地图IP接口", lambda: query_amap_ip_native(ip, AMAP_DEFAULT_KEY)))
    
    second_priority = []
    if UPSTREAM_SWITCHES["baidu_opendata"]:
        second_priority.append(("百度开放平台", lambda: query_baidu_opendata_native(ip)))
    if UPSTREAM_SWITCHES["pconline"]:
        second_priority.append(("PConline", lambda: query_pconline_native(ip)))
    
    all_upstreams = first_priority + second_priority
    if not all_upstreams:
        raise HTTPException(status_code=500, detail="无可用上游接口（已通过开关禁用所有上游）")
    
    # 强制目标格式为百度
    target_format = "baidu"
    logger.info(f"IP:{ip} - 参与竞选上游: {[name for name, _ in all_upstreams]}, 固定目标格式: {target_format}")
    
    # 按顺序尝试上游，全部转换为百度格式
    for name, func in all_upstreams:
        logger.info(f"IP:{ip} - 尝试上游：{name}，转换为百度格式")
        raw_result = func()
        if raw_result:
            formatted_result = to_baidumap_format(raw_result, ip, name)
            logger.info(f"IP:{ip} - 上游{name}响应转换为百度格式成功")
            return formatted_result
    
    raise HTTPException(status_code=503, detail="所有启用的上游接口均不可用，请稍后再试")

@app.get("/v3/ip", description="高德地图风格IP查询接口（目标格式：高德，仅高德IP接口为上游）")
async def amap_style_ip_query(
    ip: str = Query(..., description="待查询IPv4地址"),
    key: Optional[str] = Query(None, description="高德地图Key（可选，调用高德IP接口）")
) -> Dict[str, Any]:
    # 该接口逻辑无问题，保持不变
    logger.info(f"IP:{ip} - 收到高德风格查询请求，key={'提供' if key else '未提供'}")
    
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
    
    if key:
        result = query_amap_ip_native(ip, key)
        if result:
            logger.info(f"IP:{ip} - 高德IP接口返回成功（高德格式）")
            return result
        logger.warning(f"IP:{ip} - 高德IP接口失败，自动降级")
    
    logger.info(f"IP:{ip} - 无密钥/密钥无效，上游开关状态: {UPSTREAM_SWITCHES}")
    
    first_priority = []
    if AMAP_DEFAULT_KEY and UPSTREAM_SWITCHES["amap_ip"]:
        first_priority.append(("高德地图IP接口", lambda: query_amap_ip_native(ip, AMAP_DEFAULT_KEY)))
    if BAIDU_DEFAULT_AK and UPSTREAM_SWITCHES["baidu_map_ip"]:
        first_priority.append(("百度地图IP接口", lambda: query_baidu_map_ip_native(ip, "bd09ll", BAIDU_DEFAULT_AK)))
    
    second_priority = []
    if UPSTREAM_SWITCHES["baidu_opendata"]:
        second_priority.append(("百度开放平台", lambda: query_baidu_opendata_native(ip)))
    if UPSTREAM_SWITCHES["pconline"]:
        second_priority.append(("PConline", lambda: query_pconline_native(ip)))
    
    all_upstreams = first_priority + second_priority
    if not all_upstreams:
        logger.error(f"IP:{ip} - 无可用降级上游（已禁用所有上游）")
        return {
            "status": "0",
            "info": "无可用上游接口（已通过开关禁用所有上游）",
            "infocode": "10002",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": ""
        }
    
    logger.info(f"IP:{ip} - 参与竞选上游: {[name for name, _ in all_upstreams]}")
    
    for name, func in all_upstreams:
        logger.info(f"IP:{ip} - 尝试降级上游：{name}，转换为高德格式")
        raw_result = func()
        if raw_result:
            formatted_result = to_amap_format(raw_result, ip, name)
            logger.info(f"IP:{ip} - 上游{name}响应转换为高德格式成功")
            return formatted_result
    
    logger.error(f"IP:{ip} - 所有启用的降级上游均失败")
    return {
        "status": "0",
        "info": "所有启用的上游接口均不可用",
        "infocode": "10003",
        "province": "",
        "city": "",
        "adcode": "",
        "rectangle": ""
    }

@app.get("/health", description="服务健康检查接口")
async def health_check() -> Dict[str, str]:
    tz = timezone.utc
    local_time = datetime.now(tz).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    return {
        "status": "healthy",
        "version": "3.5",
        "timestamp": local_time,
        "upstream_switches": str(UPSTREAM_SWITCHES)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")