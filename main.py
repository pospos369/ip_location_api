from fastapi import FastAPI, HTTPException, Query
import requests
import re
from pydantic import BaseModel
from typing import Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="IP Location Query API")

# 定义响应模型（确保province和city必填）
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
    """验证IP地址格式，防止SQL注入和恶意输入"""
    ip_pattern = re.compile(
        r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.)'
        r'{3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    return ip_pattern.match(ip) is not None

def query_baidu_map(ip: str, coor: str, ak: Optional[str]) -> Optional[IPResponse]:
    """调用百度地图IP查询接口，处理AK无效场景"""
    if not ak:
        logger.info("未提供百度地图AK，跳过该接口")
        return None

    try:
        url = "https://api.map.baidu.com/location/ip"
        params = {"ip": ip, "coor": coor, "ak": ak}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        # 百度地图错误码处理（240: AK不存在/非法；230: AK权限不足）
        error_codes = {240, 230, 101}  # 101: 服务禁用
        if data.get("status") in error_codes:
            logger.warning(f"百度地图AK无效/受限，错误码: {data.get('status')}，切换其他接口")
            return None

        # 正常响应（status=0）且包含必要字段
        if data.get("status") == 0 and "content" in data:
            # 强制检查province和city是否存在（防止上游数据异常）
            if not all([
                data["content"]["address_detail"].get("province"),
                data["content"]["address_detail"].get("city")
            ]):
                logger.warning("百度地图返回数据缺少省市信息，跳过")
                return None
            return IPResponse(** data)

        logger.warning(f"百度地图接口返回异常状态: {data.get('status')}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"百度地图接口请求失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"百度地图接口解析失败: {str(e)}")
        return None

def query_baidu_opendata(ip: str) -> Optional[IPResponse]:
    """调用百度开放平台IP查询接口（无需AK）"""
    try:
        url = "https://opendata.baidu.com/api.php"
        params = {
            "query": ip,
            "co": "",
            "resource_id": "6006",
            "oe": "utf8"
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        if data.get("status") == "0" and data.get("data"):
            ip_data = data["data"][0]
            location = ip_data.get("location", "")
            if not location:
                logger.warning("百度开放平台未返回location信息")
                return None

            # 处理直辖市（如"北京市 电信"）和普通省市（如"广东省清远市 电信"）
            location_clean = re.sub(r'\s+[^\s]+$', '', location)  # 移除末尾运营商信息
            parts = re.split(r'[省市区]', location_clean)
            parts = [p.strip() for p in parts if p.strip()]  # 过滤空字符串

            province = parts[0] if parts else ""
            city = parts[1] if len(parts) > 1 else province  # 直辖市默认市与省同名

            if not all([province, city]):
                logger.warning(f"无法解析省市信息: {location}")
                return None

            address_detail = AddressDetail(province=province, city=city)
            content = Content(
                address=location_clean,
                address_detail=address_detail,
                point=Point()
            )
            return IPResponse(
                status=0,
                address=f"CN|{province}|{city}||None||||",
                content=content
            )

        logger.warning(f"百度开放平台接口返回异常: {data}")
        return None
    except Exception as e:
        logger.error(f"百度开放平台接口出错: {str(e)}")
        return None

def query_pconline(ip: str) -> Optional[IPResponse]:
    """调用pconline IP查询接口（无需AK）"""
    try:
        url = "http://whois.pconline.com.cn/ipJson.jsp"
        params = {"ip": ip, "json": "true"}
        response = requests.get(url, params=params, timeout=5)
        response.encoding = "gbk"  # 处理编码问题
        data = response.json()

        if data.get("err"):
            logger.warning(f"pconline接口返回错误: {data['err']}")
            return None

        province = data.get("pro", "").strip()
        city = data.get("city", "").strip()
        if not all([province, city]):
            logger.warning(f"pconline返回数据缺少省市信息: {data}")
            return None

        address_detail = AddressDetail(
            province=province,
            city=city,
            adcode=f"{data.get('proCode','')}{data.get('cityCode','')[2:]}"
        )
        content = Content(
            address=f"{province}{city}",
            address_detail=address_detail,
            point=Point()
        )
        return IPResponse(
            status=0,
            address=f"CN|{province}|{city}||None||||",
            content=content
        )
    except Exception as e:
        logger.error(f"pconline接口出错: {str(e)}")
        return None

@app.get("/location/ip", response_model=IPResponse)
async def get_ip_location(
    ip: str = Query(..., description="要查询的IP地址"),
    coor: str = Query("bd09ll", description="坐标类型，如bd09ll"),
    ak: Optional[str] = Query(None, description="百度地图API的访问密钥（可选）")
):
    """查询IP地址地理位置，支持AK无效/未提供时自动切换上游接口"""
    # 验证IP格式（防止SQL注入等恶意输入）
    if not is_valid_ip(ip):
        raise HTTPException(status_code=400, detail="无效的IP地址格式")

    # 上游接口调用顺序：百度地图（有AK时）→ 百度开放平台 → pconline
    upstream_apis = []
    if ak:
        upstream_apis.append(lambda: query_baidu_map(ip, coor, ak))
    upstream_apis.extend([
        lambda: query_baidu_opendata(ip),
        lambda: query_pconline(ip)
    ])

    # 依次尝试上游接口，返回第一个有效结果
    for api in upstream_apis:
        result = api()
        if result:
            return result

    # 所有接口失败
    raise HTTPException(status_code=503, detail="所有上游IP查询接口均不可用，请稍后再试")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)