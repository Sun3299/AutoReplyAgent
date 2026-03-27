"""
闲鱼自动回复机器人 - 测试入口
仅接收消息、获取商品信息、记录日志（不自动回复）
"""
import asyncio
import os
from dotenv import load_dotenv
from loguru import logger
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .main import XianyuLive, check_and_complete_env


def setup_logging():
    """配置日志"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )


async def main():
    """测试主函数"""
    logger.info("=" * 50)
    logger.info("闲鱼消息监听模式（仅记录，不自动回复）")
    logger.info("=" * 50)

    # 初始化
    cookies_str = os.getenv("COOKIES_STR")
    if not cookies_str:
        logger.error("未设置 COOKIES_STR 环境变量")
        return

    client = XianyuLive.get_instance(cookies_str)

    # 启动监听
    logger.info("开始监听闲鱼消息...")
    logger.info("收到消息时会打印：发送者ID、商品ID、消息内容、商品信息")
    logger.info("按 Ctrl+C 停止")
    logger.info("=" * 50)

    try:
        await client.main()
    except KeyboardInterrupt:
        logger.info("程序已停止")


if __name__ == '__main__':
    # 加载环境变量
    load_dotenv()

    # 配置日志
    setup_logging()

    # 运行
    asyncio.run(main())
