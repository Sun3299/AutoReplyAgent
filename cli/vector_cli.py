"""
向量库管理 CLI 工具

支持对商品向量库的增删改查和重建操作。
数据存储在 txt 文件中，按平台分目录。

用法:
    python -m cli.vector_cli --add -p web -f data/products/web.txt --product "产品ID: P001\n..."
    python -m cli.vector_cli --delete -p web --product-id P001
    python -m cli.vector_cli --update -p web --product-id P001 --content "新内容..."
    python -m cli.vector_cli --list -p web
    python -m cli.vector_cli --rebuild -p web
    python -m cli.vector_cli --search -p web --query "智能手表"
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# 向量库接口 (Phase 2-1 实现)
try:
    from rag.product_vector_store import ProductVectorStore
except ImportError:
    ProductVectorStore = None


PRODUCTS_DIR = Path("data/products")
SEPARATOR = "\n---\n"


def get_product_file(platform: str) -> Path:
    """获取平台对应的产品文件路径"""
    return PRODUCTS_DIR / f"{platform}.txt"


def parse_products(content: str) -> list[tuple[str, str]]:
    """
    解析 txt 文件内容
    
    Args:
        content: 文件内容
        
    Returns:
        [(product_id, product_content), ...]
    """
    products = []
    blocks = content.strip().split(SEPARATOR)
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        # 提取产品ID
        product_id = None
        for line in block.split("\n"):
            if line.startswith("产品ID:"):
                product_id = line.split(":", 1)[1].strip()
                break
        
        if product_id:
            products.append((product_id, block))
    
    return products


def format_product(product_id: str, content: str) -> str:
    """格式化产品内容"""
    return content.strip()


def read_products(platform: str) -> list[tuple[str, str]]:
    """读取平台上所有产品"""
    product_file = get_product_file(platform)
    
    if not product_file.exists():
        return []
    
    content = product_file.read_text(encoding="utf-8")
    return parse_products(content)


def write_products(platform: str, products: list[tuple[str, str]]) -> None:
    """写入产品列表到文件"""
    product_file = get_product_file(platform)
    product_file.parent.mkdir(parents=True, exist_ok=True)
    
    content = SEPARATOR.join(format_product(pid, content) for pid, content in products)
    product_file.write_text(content, encoding="utf-8")


def find_product(platform: str, product_id: str) -> Optional[tuple[str, str]]:
    """查找指定产品"""
    products = read_products(platform)
    for pid, content in products:
        if pid == product_id:
            return (pid, content)
    return None


def cmd_add(platform: str, file_path: Optional[str], product: Optional[str]) -> None:
    """添加产品"""
    if not product:
        print("错误: --product 参数 required")
        sys.exit(1)
    
    # 从内容提取产品ID
    product_id = None
    for line in product.split("\n"):
        if line.startswith("产品ID:"):
            product_id = line.split(":", 1)[1].strip()
            break
    
    if not product_id:
        print("错误: 产品内容必须包含 '产品ID:' 字段")
        sys.exit(1)
    
    # 检查是否已存在
    existing = find_product(platform, product_id)
    if existing:
        print(f"错误: 产品 {product_id} 已存在，请使用 --update 更新")
        sys.exit(1)
    
    # 读取现有产品并添加
    products = read_products(platform)
    products.append((product_id, product))
    write_products(platform, products)
    
    print(f"✓ 添加产品 {product_id} 成功")


def cmd_delete(platform: str, product_id: Optional[str]) -> None:
    """删除产品"""
    if not product_id:
        print("错误: --product-id 参数 required")
        sys.exit(1)
    
    products = read_products(platform)
    original_count = len(products)
    products = [(pid, content) for pid, content in products if pid != product_id]
    
    if len(products) == original_count:
        print(f"错误: 产品 {product_id} 不存在")
        sys.exit(1)
    
    write_products(platform, products)
    print(f"✓ 删除产品 {product_id} 成功")


def cmd_update(platform: str, product_id: Optional[str], content: Optional[str]) -> None:
    """更新产品"""
    if not product_id or not content:
        print("错误: --product-id 和 --content 参数 required")
        sys.exit(1)
    
    products = read_products(platform)
    found = False
    
    for i, (pid, _) in enumerate(products):
        if pid == product_id:
            products[i] = (product_id, content)
            found = True
            break
    
    if not found:
        print(f"错误: 产品 {product_id} 不存在")
        sys.exit(1)
    
    write_products(platform, products)
    print(f"✓ 更新产品 {product_id} 成功")


def cmd_list(platform: str) -> None:
    """列出所有产品"""
    products = read_products(platform)
    
    if not products:
        print(f"平台 '{platform}' 没有产品")
        return
    
    print(f"平台 '{platform}' 产品列表 (共 {len(products)} 个):")
    print("-" * 60)
    
    for product_id, content in products:
        # 显示产品名称
        name = "未知"
        for line in content.split("\n"):
            if line.startswith("名称:"):
                name = line.split(":", 1)[1].strip()
                break
        
        print(f"  [{product_id}] {name}")
    
    print("-" * 60)


def cmd_rebuild(platform: str) -> None:
    """重建向量库"""
    if ProductVectorStore is None:
        print("错误: ProductVectorStore 未实现 (需要 Phase 2-1)")
        sys.exit(1)
    
    print(f"正在重建平台 '{platform}' 的向量库...")
    
    try:
        vector_store = ProductVectorStore(platform=platform)
        vector_store.build_from_txt()
        print(f"✓ 向量库重建完成")
    except Exception as e:
        print(f"错误: 重建失败 - {e}")
        sys.exit(1)


def cmd_search(platform: str, query: Optional[str]) -> None:
    """测试检索"""
    if ProductVectorStore is None:
        print("错误: ProductVectorStore 未实现 (需要 Phase 2-1)")
        sys.exit(1)
    
    if not query:
        print("错误: --query 参数 required")
        sys.exit(1)
    
    try:
        vector_store = ProductVectorStore(platform=platform)
        results = vector_store.search(query, top_k=5)
        
        print(f"检索结果 (查询: '{query}'):")
        print("-" * 60)
        
        if not results:
            print("  没有找到相关产品")
        else:
            for i, doc in enumerate(results, 1):
                print(f"  {i}. [score={doc.score:.4f}] {doc.content[:100]}...")
        
        print("-" * 60)
    except Exception as e:
        print(f"错误: 检索失败 - {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="向量库管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--platform", "-p",
        required=True,
        help="平台名 (如 web, wxmp 等)"
    )
    parser.add_argument(
        "--file", "-f",
        help="txt 文件路径 (用于 --add 命令)"
    )
    parser.add_argument(
        "--add",
        action="store_true",
        help="添加产品"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="删除产品"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="更新产品"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有产品"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="重建向量库"
    )
    parser.add_argument(
        "--search",
        action="store_true",
        help="测试检索"
    )
    parser.add_argument(
        "--query",
        help="检索 query (用于 --search 命令)"
    )
    parser.add_argument(
        "--product-id",
        help="产品ID (用于 --delete/--update 命令)"
    )
    parser.add_argument(
        "--product",
        help="产品内容 (用于 --add 命令)"
    )
    parser.add_argument(
        "--content",
        help="新内容 (用于 --update 命令)"
    )
    
    args = parser.parse_args()
    
    # 确保产品目录存在
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # 解析 --content 参数 (如果通过 --update 传递)
    content = args.content or args.product
    
    # 分发命令
    if args.add:
        cmd_add(args.platform, args.file, args.product)
    elif args.delete:
        cmd_delete(args.platform, args.product_id)
    elif args.update:
        cmd_update(args.platform, args.product_id, content)
    elif args.list:
        cmd_list(args.platform)
    elif args.rebuild:
        cmd_rebuild(args.platform)
    elif args.search:
        cmd_search(args.platform, args.query)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
