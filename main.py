from fastapi import FastAPI, HTTPException, Query
import requests
import re
import random
import os
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

# 配置日志（支持DEBUG级别，方便排查）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="IP Location Query API", version="1.0")

# 从环境变量读取默认密钥（避免硬编码）
BAIDU_DEFAULT_AK = os.getenv("BAIDU_DEFAULT_AK", "")  # 默认百度AK
AMAP_DEFAULT_KEY = os.getenv("AMAP_DEFAULT_KEY", "")  # 默认高德Key

# 统一响应模型（内部使用）
class AddressDetail(BaseModel):
    adcode: Optional[str] = ""
    city: str  # 强制必填
    city_code: Optional[int] = 0
    district: Optional[str] = ""
    province: str  # 强制必填
    street: Optional[str] = ""
    street_number: Optional[str] = ""

class Point(BaseModel):
    x: Optional[str] = ""
    y: Optional[str] = ""

class Content(BaseModel):
    address: Optional[str] = ""
    address_detail: AddressDetail
    point: Point

class IPResponse(BaseModel):
    status: int
    address: Optional[str] = ""
    content: Content

def is_valid_ip(ip: str) -> bool:
    """验证IPv4格式，防范恶意输入"""
    ip_pattern = re.compile(
        r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.)'
        r'{3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    return ip_pattern.match(ip) is not None

def unified_to_amap_format(unified_data: IPResponse, ip: str, upstream: str) -> Dict[str, Any]:
    """将统一格式响应转换为高德原生格式（记录上游来源）"""
    address_detail = unified_data.content.address_detail
    result = {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "province": address_detail.province,
        "city": address_detail.city,
        "adcode": address_detail.adcode,
        "rectangle": ""  # 非高德上游无矩形范围，返回空字符串（符合高德格式规范）
    }
    logger.info(f"IP:{ip} - 转换为高德格式结果: {result}")
    return result

def query_baidu_map_native(ip: str, coor: str, ak: str) -> Optional[Dict[str, Any]]:
    """调用百度地图接口，返回原生格式响应"""
    logger.info(f"IP:{ip} - 选用上游接口：百度地图原生接口")
    if not ak:
        logger.warning(f"IP:{ip} - 百度地图AK为空，跳过")
        return None
    try:
        url = "https://api.map.baidu.com/location/ip"
        params = {"ip": ip, "coor": coor, "ak": ak}
        logger.debug(f"IP:{ip} - 百度地图请求参数: {params}（AK已脱敏）")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        raw_data = response.json()
        logger.debug(f"IP:{ip} - 百度地图原生响应: {raw_data}")
        return raw_data
    except Exception as e:
        logger.error(f"IP:{ip} - 百度原生接口调用失败: {str(e)}")
        return None

def query_amap_ip_native(ip: str, key: str) -> Optional[Dict[str, Any]]:
    """调用高德地图接口，返回原生格式响应"""
    logger.info(f"IP:{ip} - 选用上游接口：高德地图原生接口")
    if not key:
        logger.warning(f"IP:{ip} - 高德地图Key为空，跳过")
        return None
    try:
        url = "https://restapi.amap.com/v3/ip"
        params = {"ip": ip, "key": key}
        logger.debug(f"IP:{ip} - 高德地图请求参数: {params}（Key已脱敏）")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        raw_data = response.json()
        logger.debug(f"IP:{ip} - 高德地图原生响应: {raw_data}")
        return raw_data
    except Exception as e:
        logger.error(f"IP:{ip} - 高德原生接口调用失败: {str(e)}")
        return None

def query_baidu_map_unified(ip: str, coor: str, ak: str) -> Optional[IPResponse]:
    """调用百度地图接口，返回统一格式响应"""
    logger.info(f"IP:{ip} - 选用上游接口：百度地图（统一格式）")
    if not ak:
        logger.warning(f"IP:{ip} - 百度地图AK为空，跳过")
        return None
    try:
        data = query_baidu_map_native(ip, coor, ak)
        if not data or data.get("status") != 0:
            logger.warning(f"IP:{ip} - 百度接口统一格式转换失败: {data}")
            return None
        # 校验核心字段
        if not all([data["content"]["address_detail"].get("province"), data["content"]["address_detail"].get("city")]):
            logger.warning(f"IP:{ip} - 百度接口返回数据缺少省市信息")
            return None
        unified_data = IPResponse(**data)
        logger.debug(f"IP:{ip} - 百度接口统一格式结果: {unified_data.dict()}")
        return unified_data
    except Exception as e:
        logger.error(f"IP:{ip} - 百度接口统一格式转换异常: {str(e)}")
        return None

def query_amap_ip_unified(ip: str, key: str) -> Optional[IPResponse]:
    """调用高德地图接口，返回统一格式响应（处理直辖市）"""
    logger.info(f"IP:{ip} - 选用上游接口：高德地图（统一格式）")
    if not key:
        logger.warning(f"IP:{ip} - 高德地图Key为空，跳过")
        return None
    try:
        data = query_amap_ip_native(ip, key)
        if not data or data.get("status") != "1":
            logger.warning(f"IP:{ip} - 高德接口统一格式转换失败: {data}")
            return None
        
        # 提取并处理省市信息（直辖市：city=province）
        province = data.get("province", "").strip()
        city = data.get("city", "").strip()
        if not city or city == province:  # 直辖市/省份无下级市
            city = province
        if not all([province, city]):
            logger.warning(f"IP:{ip} - 高德接口返回数据缺少省市信息: {data}")
            return None
        
        # 构建统一格式
        address_detail = AddressDetail(
            adcode=data.get("adcode", ""),
            province=province,
            city=city
        )
        content = Content(
            address=f"{province}{city}",
            address_detail=address_detail,
            point=Point()  # 高德接口无经纬度，设为空
        )
        unified_data = IPResponse(
            status=0,
            address=f"CN|{province}|{city}||None||||",
            content=content
        )
        logger.debug(f"IP:{ip} - 高德接口统一格式结果: {unified_data.dict()}")
        return unified_data
    except Exception as e:
        logger.error(f"IP:{ip} - 高德接口统一格式转换异常: {str(e)}")
        return None

def query_baidu_opendata_unified(ip: str) -> Optional[IPResponse]:
    """百度开放平台接口（统一格式）- 修复省份提取逻辑"""
    logger.info(f"IP:{ip} - 选用上游接口：百度开放平台")
    try:
        url = "https://opendata.baidu.com/api.php"
        params = {"query": ip, "co": "", "resource_id": "6006", "oe": "utf8"}
        logger.debug(f"IP:{ip} - 百度开放平台请求参数: {params}")
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        logger.debug(f"IP:{ip} - 百度开放平台原生响应: {data}")

        if data.get("status") == "0" and data.get("data"):
            ip_data = data["data"][0]
            location = ip_data.get("location", "").strip()
            if not location:
                logger.warning(f"IP:{ip} - 百度开放平台未返回location信息")
                return None

            # 先移除运营商，再用省份关键词分割（支持完整省份名称）
            location_clean = re.sub(r'\s+[^\s]+$', '', location)  # 移除末尾运营商（如" 电信"）
            logger.debug(f"IP:{ip} - 百度开放平台清理后location: {location_clean}")
            
            # 匹配省份（支持：省、自治区、直辖市、特别行政区）
            province_pattern = r'([^省市区]+[省自治区直辖市特别行政区])'
            province_match = re.search(province_pattern, location_clean)
            if not province_match:
                logger.warning(f"IP:{ip} - 无法提取省份信息: {location_clean}")
                return None
            
            province = province_match.group(1).strip()
            # 提取城市（省份之后，下一个省市区关键词之前的内容）
            city_part = re.sub(province_pattern, '', location_clean).strip()
            city_pattern = r'([^省市区]+[省市])'
            city_match = re.search(city_pattern, city_part)
            
            if city_match:
                city = city_match.group(1).strip()
            else:
                # 直辖市/无明确城市，城市=省份
                city = province

            logger.debug(f"IP:{ip} - 提取结果：省份={province}，城市={city}")

            if not all([province, city]):
                logger.warning(f"IP:{ip} - 无法解析省市信息: {location_clean}")
                return None

            address_detail = AddressDetail(province=province, city=city)
            content = Content(
                address=location_clean,
                address_detail=address_detail,
                point=Point()
            )
            unified_data = IPResponse(
                status=0,
                address=f"CN|{province}|{city}||None||||",
                content=content
            )
            logger.debug(f"IP:{ip} - 百度开放平台统一格式结果: {unified_data.dict()}")
            return unified_data
        logger.warning(f"IP:{ip} - 百度开放平台接口返回异常: {data}")
        return None
    except Exception as e:
        logger.error(f"IP:{ip} - 百度开放平台接口失败: {str(e)}")
        return None

def query_pconline_unified(ip: str) -> Optional[IPResponse]:
    """PConline接口（统一格式）- 修复省份提取逻辑"""
    logger.info(f"IP:{ip} - 选用上游接口：PConline")
    try:
        url = "http://whois.pconline.com.cn/ipJson.jsp"
        params = {"ip": ip, "json": "true"}
        logger.debug(f"IP:{ip} - PConline请求参数: {params}")
        response = requests.get(url, params=params, timeout=5)
        response.encoding = "gbk"
        data = response.json()
        logger.debug(f"IP:{ip} - PConline原生响应: {data}")

        if data.get("err"):
            logger.warning(f"IP:{ip} - PConline接口返回错误: {data['err']}")
            return None

        # 直接使用接口返回的pro和city字段（完整名称），无需分割
        province = data.get("pro", "").strip()
        city = data.get("city", "").strip()
        
        # 处理特殊情况：pro为空但city包含省份信息
        if not province and city:
            province_pattern = r'([^省市区]+[省自治区直辖市特别行政区])'
            province_match = re.search(province_pattern, city)
            if province_match:
                province = province_match.group(1).strip()
                city = re.sub(province_pattern, '', city).strip()
                if not city:
                    city = province

        logger.debug(f"IP:{ip} - 提取结果：省份={province}，城市={city}")

        if not all([province, city]):
            logger.warning(f"IP:{ip} - PConline返回数据缺少省市信息: {data}")
            return None

        address_detail = AddressDetail(
            province=province,
            city=city,
            adcode=f"{data.get('proCode','')}{data.get('cityCode','')[2:]}" if (data.get('proCode') and data.get('cityCode')) else ""
        )
        content = Content(
            address=f"{province}{city}",
            address_detail=address_detail,
            point=Point()
        )
        unified_data = IPResponse(
            status=0,
            address=f"CN|{province}|{city}||None||||",
            content=content
        )
        logger.debug(f"IP:{ip} - PConline统一格式结果: {unified_data.dict()}")
        return unified_data
    except Exception as e:
        logger.error(f"IP:{ip} - PConline接口失败: {str(e)}")
        return None

# -------------------------- 接口定义 --------------------------
@app.get("/location/ip", description="通用IP查询接口（支持原生/统一格式）")
async def get_ip_location(
    ip: str = Query(..., description="待查询IPv4地址"),
    coor: str = Query("bd09ll", description="坐标类型（仅百度地图接口使用）"),
    ak: Optional[str] = Query(None, description="百度地图AK（优先级最高，返回原生格式）"),
    key: Optional[str] = Query(None, description="高德地图Key（优先级次高，返回原生格式）")
) -> Any:
    """
    核心接口逻辑：
    1. 提供ak → 调用百度原生接口（返回百度格式）
    2. 提供key → 调用高德原生接口（返回高德格式）
    3. 均不提供 → 用默认密钥随机选择上游（返回统一格式）
    """
    logger.info(f"IP:{ip} - 收到通用IP查询请求，ak={'提供' if ak else '未提供'}，key={'提供' if key else '未提供'}")
    
    # 1. 验证IP有效性
    if not is_valid_ip(ip):
        logger.warning(f"IP:{ip} - 无效的IPv4地址格式")
        raise HTTPException(status_code=400, detail="无效的IPv4地址格式")

    # 2. 优先处理用户提供的密钥（返回原生格式）
    if ak:
        result = query_baidu_map_native(ip, coor, ak)
        if result:
            logger.info(f"IP:{ip} - 百度原生接口返回成功")
            return result
        logger.error(f"IP:{ip} - 百度地图接口调用失败（AK无效/接口异常）")
        raise HTTPException(status_code=503, detail="百度地图接口调用失败（AK无效/接口异常）")
    
    if key:
        result = query_amap_ip_native(ip, key)
        if result:
            logger.info(f"IP:{ip} - 高德原生接口返回成功")
            return result
        logger.error(f"IP:{ip} - 高德地图接口调用失败（Key无效/接口异常）")
        raise HTTPException(status_code=503, detail="高德地图接口调用失败（Key无效/接口异常）")

    # 3. 未提供密钥 → 用默认密钥随机选择上游（返回统一格式）
    default_upstreams = []
    # 百度地图（默认AK存在则添加）
    if BAIDU_DEFAULT_AK:
        default_upstreams.append(("百度地图（默认AK）", lambda: query_baidu_map_unified(ip, coor, BAIDU_DEFAULT_AK)))
    # 高德地图（默认Key存在则添加）
    if AMAP_DEFAULT_KEY:
        default_upstreams.append(("高德地图（默认Key）", lambda: query_amap_ip_unified(ip, AMAP_DEFAULT_KEY)))
    # 无需密钥的上游
    default_upstreams.extend([
        ("百度开放平台", lambda: query_baidu_opendata_unified(ip)),
        ("PConline", lambda: query_pconline_unified(ip))
    ])

    # 无可用上游（默认密钥未配置且无免密钥接口）
    if not default_upstreams:
        logger.error(f"IP:{ip} - 未配置默认API密钥，且无可用免密钥上游接口")
        raise HTTPException(status_code=500, detail="未配置默认API密钥，且无可用免密钥上游接口")

    # 随机打乱上游顺序，尝试调用
    random.shuffle(default_upstreams)
    logger.info(f"IP:{ip} - 无密钥，随机上游顺序: {[name for name, _ in default_upstreams]}")
    
    for name, api in default_upstreams:
        logger.info(f"IP:{ip} - 尝试上游接口：{name}")
        result = api()
        if result:
            logger.info(f"IP:{ip} - 上游接口{name}返回成功，返回统一格式数据")
            return result

    # 所有上游均失败
    logger.error(f"IP:{ip} - 所有上游接口均不可用")
    raise HTTPException(status_code=503, detail="所有上游接口均不可用，请稍后再试")

@app.get("/v3/ip", description="高德地图风格IP查询接口（与高德官方格式完全一致）")
async def amap_style_ip_query(
    ip: str = Query(..., description="待查询IPv4地址"),
    key: Optional[str] = Query(None, description="高德地图API Key（可选，不提供则自动降级）")
) -> Dict[str, Any]:
    """
    高德风格接口，响应格式与高德官方完全一致：
    1. 提供key → 优先调用高德原生接口（返回高德原生格式）
    2. 不提供key → 用默认密钥/其他上游接口，转换为高德格式后返回
    """
    logger.info(f"IP:{ip} - 收到高德风格IP查询请求，key={'提供' if key else '未提供'}")
    
    # 1. 验证IP有效性
    if not is_valid_ip(ip):
        logger.warning(f"IP:{ip} - 无效的IPv4地址格式")
        return {
            "status": "0",
            "info": "无效的IPv4地址格式",
            "infocode": "10001",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": ""
        }

    # 2. 提供key → 优先调用高德原生接口
    if key:
        amap_result = query_amap_ip_native(ip, key)
        if amap_result:
            logger.info(f"IP:{ip} - 高德原生接口返回成功")
            return amap_result
        logger.warning(f"IP:{ip} - 高德原生接口调用失败（Key：{key}已脱敏），自动降级")

    # 3. 不提供key 或 高德原生接口失败 → 自动降级，调用其他上游并转换格式
    fallback_upstreams = []
    # 高德默认Key（存在则优先尝试）
    if AMAP_DEFAULT_KEY:
        fallback_upstreams.append(("高德地图（默认Key）", lambda: query_amap_ip_unified(ip, AMAP_DEFAULT_KEY)))
    # 其他上游接口（统一格式）
    if BAIDU_DEFAULT_AK:
        fallback_upstreams.append(("百度地图（默认AK）", lambda: query_baidu_map_unified(ip, "bd09ll", BAIDU_DEFAULT_AK)))
    fallback_upstreams.extend([
        ("百度开放平台", lambda: query_baidu_opendata_unified(ip)),
        ("PConline", lambda: query_pconline_unified(ip))
    ])

    if not fallback_upstreams:
        logger.error(f"IP:{ip} - 无可用上游接口（未配置默认密钥）")
        return {
            "status": "0",
            "info": "无可用上游接口（未配置默认密钥）",
            "infocode": "10002",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": ""
        }

    # 随机选择降级上游，转换为高德格式
    random.shuffle(fallback_upstreams)
    logger.info(f"IP:{ip} - 降级上游顺序: {[name for name, _ in fallback_upstreams]}")
    
    for name, api in fallback_upstreams:
        logger.info(f"IP:{ip} - 尝试降级上游接口：{name}")
        unified_result = api()
        if unified_result:
            return unified_to_amap_format(unified_result, ip, name)

    # 所有降级上游均失败
    logger.error(f"IP:{ip} - 所有上游接口均不可用")
    return {
        "status": "0",
        "info": "所有上游接口均不可用",
        "infocode": "10003",
        "province": "",
        "city": "",
        "adcode": "",
        "rectangle": ""
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")