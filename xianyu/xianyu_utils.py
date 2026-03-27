import json
import time
import hashlib
import base64
import struct
from typing import Any, Dict, List


def trans_cookies(cookies_str: str) -> Dict[str, str]:
    """
    解析浏览器/接口返回的Cookie字符串为Python字典

    Args:
        cookies_str: Cookie字符串，格式如 "name1=value1; name2=value2"

    Returns:
        解析后的Cookie字典，键值对形式存储Cookie信息
    """
    cookies = {}
    # 按 "; " 或 ";" 分割每个Cookie项
    for cookie in cookies_str.replace('; ', ';').split(';'):
        try:
            # 按第一个 "=" 分割，避免值中包含"="导致解析错误
            parts = cookie.split('=', 1)
            if len(parts) == 2:
                cookies[parts[0]] = parts[1]
        except:
            # 忽略解析失败的Cookie项
            continue
    return cookies


def generate_mid() -> str:
    """
    生成闲鱼接口所需的mid标识（设备中间标识）
    格式：随机数 + 时间戳(毫秒) + " 0"

    Returns:
        生成的mid字符串
    """
    import random
    # 生成0-999的随机整数
    random_part = int(1000 * random.random())
    # 获取当前时间戳（毫秒级）
    timestamp = int(time.time() * 1000)
    return f"{random_part}{timestamp} 0"


def generate_uuid() -> str:
    """
    生成简化版UUID（闲鱼接口专用）
    格式："-" + 时间戳(毫秒) + "1"

    Returns:
        生成的UUID字符串
    """
    timestamp = int(time.time() * 1000)
    return f"-{timestamp}1"


def generate_device_id(user_id: str) -> str:
    """
    生成符合RFC4122标准的UUID格式设备ID，最后拼接用户ID
    格式：8-4-4-4-12的UUID + "-" + 用户ID

    Args:
        user_id: 用户唯一标识

    Returns:
        完整的设备ID字符串
    """
    import random

    # UUID允许的字符集（数字+大小写字母）
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    result = []

    # 生成36位UUID字符（包含4个分隔符"-"）
    for i in range(36):
        # 固定位置添加分隔符
        if i in [8, 13, 18, 23]:
            result.append("-")
        # 第14位固定为"4"（UUID版本号标识）
        elif i == 14:
            result.append("4")
        else:
            # 第19位做特殊处理（UUID变体标识）
            if i == 19:
                rand_val = int(16 * random.random())
                # 确保第19位是8/9/a/b中的一个
                result.append(chars[(rand_val & 0x3) | 0x8])
            else:
                # 其他位置随机取字符
                rand_val = int(16 * random.random())
                result.append(chars[rand_val])

    # 拼接用户ID，形成最终的设备ID
    return ''.join(result) + "-" + user_id


def generate_sign(t: str, token: str, data: str) -> str:
    """
    生成闲鱼接口请求的签名（防篡改验证）
    签名规则：MD5(token&时间戳&app_key&请求数据)

    Args:
        t: 时间戳字符串（毫秒级）
        token: 接口调用令牌（从Cookie的_m_h5_tk中提取）
        data: 请求的JSON数据字符串

    Returns:
        32位MD5签名字符串（小写）
    """
    # 闲鱼固定的app_key（接口标识）
    app_key = "34839810"
    # 按闲鱼规则拼接签名原文
    msg = f"{token}&{t}&{app_key}&{data}"

    # 使用MD5算法生成签名
    md5_hash = hashlib.md5()
    md5_hash.update(msg.encode('utf-8'))
    return md5_hash.hexdigest()


class MessagePackDecoder:
    """
    MessagePack解码器纯Python实现
    MessagePack是一种高效的二进制序列化格式，比JSON更小更快
    用于解析闲鱼接口返回的二进制数据
    """

    def __init__(self, data: bytes):
        """
        初始化解码器

        Args:
            data: 待解码的MessagePack二进制数据
        """
        self.data = data  # 原始二进制数据
        self.pos = 0  # 当前读取位置指针
        self.length = len(data)  # 数据总长度

    def read_byte(self) -> int:
        """读取单个字节并移动指针"""
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")  # 数据读取完毕
        byte = self.data[self.pos]
        self.pos += 1
        return byte

    def read_bytes(self, count: int) -> bytes:
        """读取指定长度的字节串并移动指针"""
        if self.pos + count > self.length:
            raise ValueError("Unexpected end of data")  # 剩余数据不足
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result

    def read_uint8(self) -> int:
        """读取无符号8位整数（1字节）"""
        return self.read_byte()

    def read_uint16(self) -> int:
        """读取无符号16位整数（2字节，大端序）"""
        return struct.unpack('>H', self.read_bytes(2))[0]

    def read_uint32(self) -> int:
        """读取无符号32位整数（4字节，大端序）"""
        return struct.unpack('>I', self.read_bytes(4))[0]

    def read_uint64(self) -> int:
        """读取无符号64位整数（8字节，大端序）"""
        return struct.unpack('>Q', self.read_bytes(8))[0]

    def read_int8(self) -> int:
        """读取有符号8位整数（1字节）"""
        return struct.unpack('>b', self.read_bytes(1))[0]

    def read_int16(self) -> int:
        """读取有符号16位整数（2字节，大端序）"""
        return struct.unpack('>h', self.read_bytes(2))[0]

    def read_int32(self) -> int:
        """读取有符号32位整数（4字节，大端序）"""
        return struct.unpack('>i', self.read_bytes(4))[0]

    def read_int64(self) -> int:
        """读取有符号64位整数（8字节，大端序）"""
        return struct.unpack('>q', self.read_bytes(8))[0]

    def read_float32(self) -> float:
        """读取32位浮点数（4字节，大端序）"""
        return struct.unpack('>f', self.read_bytes(4))[0]

    def read_float64(self) -> float:
        """读取64位浮点数（8字节，大端序）"""
        return struct.unpack('>d', self.read_bytes(8))[0]

    def read_string(self, length: int) -> str:
        """读取指定长度的UTF-8字符串"""
        return self.read_bytes(length).decode('utf-8')

    def decode_value(self) -> Any:
        """
        核心解码方法：根据MessagePack格式字节解析对应的值
        支持的类型：整数、布尔、字符串、二进制、数组、字典、浮点数、空值等
        """
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")

        # 读取格式标识字节（MessagePack的核心，不同字节对应不同类型）
        format_byte = self.read_byte()

        # 1. 正整数（0xxxxxxx）：直接返回数值
        if format_byte <= 0x7f:
            return format_byte

        # 2. 字典（1000xxxx）：解析指定长度的键值对
        elif 0x80 <= format_byte <= 0x8f:
            size = format_byte & 0x0f  # 提取低4位作为字典长度
            return self.decode_map(size)

        # 3. 数组（1001xxxx）：解析指定长度的数组元素
        elif 0x90 <= format_byte <= 0x9f:
            size = format_byte & 0x0f  # 提取低4位作为数组长度
            return self.decode_array(size)

        # 4. 短字符串（101xxxxx）：解析指定长度的字符串
        elif 0xa0 <= format_byte <= 0xbf:
            size = format_byte & 0x1f  # 提取低5位作为字符串长度
            return self.read_string(size)

        # 5. 空值
        elif format_byte == 0xc0:
            return None

        # 6. 布尔值-False
        elif format_byte == 0xc2:
            return False

        # 7. 布尔值-True
        elif format_byte == 0xc3:
            return True

        # 8. 二进制数据-8位长度
        elif format_byte == 0xc4:
            size = self.read_uint8()
            return self.read_bytes(size)

        # 9. 二进制数据-16位长度
        elif format_byte == 0xc5:
            size = self.read_uint16()
            return self.read_bytes(size)

        # 10. 二进制数据-32位长度
        elif format_byte == 0xc6:
            size = self.read_uint32()
            return self.read_bytes(size)

        # 11. 32位浮点数
        elif format_byte == 0xca:
            return self.read_float32()

        # 12. 64位浮点数
        elif format_byte == 0xcb:
            return self.read_float64()

        # 13. 无符号8位整数
        elif format_byte == 0xcc:
            return self.read_uint8()

        # 14. 无符号16位整数
        elif format_byte == 0xcd:
            return self.read_uint16()

        # 15. 无符号32位整数
        elif format_byte == 0xce:
            return self.read_uint32()

        # 16. 无符号64位整数
        elif format_byte == 0xcf:
            return self.read_uint64()

        # 17. 有符号8位整数
        elif format_byte == 0xd0:
            return self.read_int8()

        # 18. 有符号16位整数
        elif format_byte == 0xd1:
            return self.read_int16()

        # 19. 有符号32位整数
        elif format_byte == 0xd2:
            return self.read_int32()

        # 20. 有符号64位整数
        elif format_byte == 0xd3:
            return self.read_int64()

        # 21. 字符串-8位长度
        elif format_byte == 0xd9:
            size = self.read_uint8()
            return self.read_string(size)

        # 22. 字符串-16位长度
        elif format_byte == 0xda:
            size = self.read_uint16()
            return self.read_string(size)

        # 23. 字符串-32位长度
        elif format_byte == 0xdb:
            size = self.read_uint32()
            return self.read_string(size)

        # 24. 数组-16位长度
        elif format_byte == 0xdc:
            size = self.read_uint16()
            return self.decode_array(size)

        # 25. 数组-32位长度
        elif format_byte == 0xdd:
            size = self.read_uint32()
            return self.decode_array(size)

        # 26. 字典-16位长度
        elif format_byte == 0xde:
            size = self.read_uint16()
            return self.decode_map(size)

        # 27. 字典-32位长度
        elif format_byte == 0xdf:
            size = self.read_uint32()
            return self.decode_map(size)

        # 28. 负整数（111xxxxx）：转换为有符号整数
        elif format_byte >= 0xe0:
            return format_byte - 256  # 转换为负数

        # 未知格式
        else:
            raise ValueError(f"Unknown format byte: 0x{format_byte:02x}")

    def decode_array(self, size: int) -> List[Any]:
        """
        解码MessagePack数组

        Args:
            size: 数组元素个数

        Returns:
            解析后的Python列表
        """
        result = []
        for _ in range(size):
            result.append(self.decode_value())  # 递归解码每个元素
        return result

    def decode_map(self, size: int) -> Dict[Any, Any]:
        """
        解码MessagePack字典

        Args:
            size: 字典键值对个数

        Returns:
            解析后的Python字典
        """
        result = {}
        for _ in range(size):
            key = self.decode_value()  # 递归解码键
            value = self.decode_value()  # 递归解码值
            result[key] = value
        return result

    def decode(self) -> Any:
        """
        对外暴露的解码入口

        Returns:
            解析后的Python对象（字典/列表/字符串等），解码失败则返回base64编码的原始数据
        """
        try:
            return self.decode_value()
        except Exception as e:
            # 解码失败时返回原始数据的base64编码，便于调试
            return base64.b64encode(self.data).decode('utf-8')


def decrypt(data: str) -> str:
    """
    闲鱼接口加密数据解密主函数
    解密流程：Base64解码 → MessagePack解析 → JSON格式化
    失败时会降级处理（字符串解析 → 十六进制 → 错误信息）

    Args:
        data: 接口返回的加密字符串

    Returns:
        格式化后的JSON字符串（包含解密结果或错误信息）
    """
    try:
        # ========== 第一步：清理并解码Base64数据 ==========
        # 过滤非Base64字符，避免解码失败
        cleaned_data = ''.join(
            c for c in data if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')

        # 补全Base64填充符（必须是4的倍数长度）
        while len(cleaned_data) % 4 != 0:
            cleaned_data += '='

        try:
            # Base64解码为二进制数据
            decoded_bytes = base64.b64decode(cleaned_data)
        except Exception as e:
            # Base64解码失败，返回错误信息
            return json.dumps({"error": f"Base64 decode failed: {str(e)}", "raw_data": data})

        # ========== 第二步：尝试MessagePack解码 ==========
        try:
            decoder = MessagePackDecoder(decoded_bytes)
            result = decoder.decode()

            # ========== 第三步：转换为JSON字符串 ==========
            def json_serializer(obj):
                """
                自定义JSON序列化器
                处理特殊类型（字节串、对象等）的序列化
                """
                if isinstance(obj, bytes):
                    # 字节串优先尝试UTF-8解码，失败则转Base64
                    try:
                        return obj.decode('utf-8')
                    except:
                        return base64.b64encode(obj).decode('utf-8')
                elif hasattr(obj, '__dict__'):
                    # 自定义对象序列化（取属性字典）
                    return obj.__dict__
                else:
                    # 其他类型转为字符串
                    return str(obj)

            # 生成带中文的格式化JSON
            return json.dumps(result, ensure_ascii=False, default=json_serializer)

        except Exception as e:
            # MessagePack解码失败，尝试直接解析为字符串
            try:
                text_result = decoded_bytes.decode('utf-8')
                return json.dumps({"text": text_result})
            except:
                # 最终降级方案：返回十六进制和错误信息
                hex_result = decoded_bytes.hex()
                return json.dumps({"hex": hex_result, "error": f"Decode failed: {str(e)}"})

    except Exception as e:
        # 全局异常捕获，返回原始数据和错误信息
        return json.dumps({"error": f"Decrypt failed: {str(e)}", "raw_data": data})