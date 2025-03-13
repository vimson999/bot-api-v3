#!/usr/bin/env python3
"""
飞书Token验证命令行工具

用法:
  python verify_feishu_sheet_token.py <token> [--debug] [--timeout SECONDS] [--key-file KEY_FILE]
  
示例:
  python verify_feishu_sheet_token.py "eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI..." --debug
"""

import sys
import os
import argparse
import json
import time
import logging
from datetime import datetime
from bot_api_v1.app.core.logger import logger

# 确保能够导入飞书签名验证模块
try:
    # 优先尝试从项目包导入
    from bot_api_v1.app.security.signature.providers.feishu_sheet import verify_feishu_token, rsa_verify_sign
except ImportError:
    try:
        # 尝试从本地目录导入
        from bot_api_v1.app.security.signature.providers.feishu_sheet import verify_feishu_token, rsa_verify_sign
    except ImportError:
        sys.stderr.write("错误: 无法导入飞书签名验证模块。请确保该模块可用。\n")
        sys.exit(1)


def format_json(json_data):
    """格式化JSON数据"""
    return json.dumps(json_data, ensure_ascii=False, indent=2)

def load_public_key(key_file):
    """从文件加载公钥"""
    try:
        with open(key_file, 'r') as f:
            return f.read().strip()
    except Exception as e:
        sys.stderr.write(f"错误: 无法从 {key_file} 加载公钥: {e}\n")
        sys.exit(1)

def format_timestamp(timestamp):
    """将时间戳格式化为人类可读的日期时间"""
    try:
        # 处理毫秒级时间戳
        if timestamp > 1000000000000:  # 大于2001年，可能是毫秒
            timestamp = timestamp / 1000
        
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(timestamp)  # 如果转换失败，返回原始值

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='验证飞书Token')
    parser.add_argument('token', help='要验证的飞书Token')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    parser.add_argument('--timeout', type=float, default=5.0, help='验证超时时间(秒)')
    parser.add_argument('--key-file', help='从文件加载公钥')
    
    args = parser.parse_args()
    
    
    # 从文件加载公钥(如果指定)
    public_key = None
    if args.key_file:
        public_key = load_public_key(args.key_file)
    
    logger.info("开始验证飞书Token...")
    start_time = time.time()
    
    # 验证token
    valid, data = verify_feishu_token(
        args.token, 
        debug=args.debug,
        public_key=public_key,
        timeout=args.timeout
    )
    
    duration = time.time() - start_time
    
    # 输出结果
    if valid:
        print("\n✅ 验证成功!")
        print(f"耗时: {duration:.4f}秒")
        
        if isinstance(data, dict):
            # 处理过期时间
            if 'exp' in data:
                exp_time = format_timestamp(data['exp'])
                data['exp_formatted'] = exp_time
                
                # 检查token是否过期
                now = time.time()
                exp = data['exp']
                if exp > 1000000000000:  # 毫秒级时间戳
                    exp = exp / 1000
                    
                if now > exp:
                    print("\n⚠️ 警告: 此Token已过期!")
                    print(f"过期时间: {exp_time}")
                    print(f"当前时间: {format_timestamp(int(now))}")
                else:
                    print(f"\n有效期至: {exp_time}")
            
            # 显示格式化后的数据
            print("\n解码数据:")
            print(format_json(data))
        else:
            print("\n解码数据:")
            print(data)
    else:
        print("\n❌ 验证失败!")
        print(f"耗时: {duration:.4f}秒")
        sys.exit(1)

if __name__ == '__main__':
    main()