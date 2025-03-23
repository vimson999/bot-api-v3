#!/usr/bin/env python3
"""
小红书服务类测试脚本
用于测试 xhs_service.py 的新实现

使用方法:
python -m src.bot_api_v1.tests.test_n_xhs_service

或从项目根目录执行:
python src/bot_api_v1/tests/test_n_xhs_service.py
"""
import os
import sys
import asyncio
import json
from pathlib import Path
import unittest

# 确保可以导入项目代码
ROOT_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 导入要测试的服务
from src.bot_api_v1.app.services.business.xhs_service import XHSService, XHSError

# 测试用的URL和ID
TEST_NOTE_URL = "https://www.xiaohongshu.com/explore/64674a91000000001301762e"
TEST_USER_URL = "https://www.xiaohongshu.com/user/profile/5a6b47644eacab3de7975ddf"
TEST_USER_ID = "5a6b47644eacab3de7975ddf"

# 自定义Cookie文件路径（如果有）
COOKIE_FILE_PATH = os.getenv("XHS_COOKIE_PATH", None)

class TestXHSService(unittest.TestCase):
    """小红书服务测试类"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 创建服务实例和异步事件循环"""
        cls.service = XHSService(
            api_timeout=30, 
            cache_duration=60,  # 测试时使用较短的缓存时间
            cookies_file=COOKIE_FILE_PATH
        )
        
        # 检查服务实例是否正确初始化
        assert cls.service is not None, "无法创建XHSService实例"
        
        # 创建异步事件循环
        cls.loop = asyncio.get_event_loop()
        
        # 检查Cookie是否已加载
        if not cls.service.cookies_str:
            print("\n警告: 无法加载小红书Cookie，测试可能会失败")
    
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        # 关闭事件循环
        if hasattr(cls, 'loop') and cls.loop.is_running():
            cls.loop.close()
    
    def run_async(self, coro):
        """运行协程并返回结果"""
        return self.loop.run_until_complete(coro)
    
    def test_01_service_initialization(self):
        """测试服务初始化"""
        print("\n测试服务初始化...")
        
        # 检查关键属性是否存在
        self.assertIsNotNone(self.service.xhs_apis)
        self.assertIsNotNone(self.service.script_service)
        self.assertIsNotNone(self.service.base_path)
        
        # 检查下载目录是否存在
        media_dir = self.service.base_path.get("media")
        self.assertIsNotNone(media_dir)
        self.assertTrue(os.path.exists(media_dir))
        
        print(f"服务初始化成功，媒体目录: {media_dir}")
    
    def test_02_get_note_info_basic(self):
        """测试获取笔记基本信息"""
        print("\n测试获取笔记基本信息...")
        
        # 获取笔记信息 - 不提取文案
        try:
            note_info = self.run_async(
                self.service.get_note_info(TEST_NOTE_URL, extract_text=False)
            )
            
            # 验证笔记信息的基本结构
            self.assertIsNotNone(note_info)
            self.assertIn("note_id", note_info)
            self.assertIn("title", note_info)
            self.assertIn("desc", note_info)
            self.assertIn("type", note_info)
            self.assertIn("author", note_info)
            self.assertIn("statistics", note_info)
            self.assertIn("media", note_info)
            
            # 检查关键信息
            self.assertTrue(len(note_info["note_id"]) > 0)
            self.assertTrue(len(note_info["title"]) > 0)
            
            # 打印基本信息
            print(f"笔记ID: {note_info['note_id']}")
            print(f"标题: {note_info['title']}")
            print(f"描述: {note_info['desc'][:50]}..." if len(note_info['desc']) > 50 else note_info['desc'])
            print(f"类型: {note_info['type']}")
            print(f"作者: {note_info['author']['nickname']}")
            print(f"媒体类型: {note_info['media']['type']}")
            
            # 验证统计信息结构
            self.assertIn("like_count", note_info["statistics"])
            self.assertIn("comment_count", note_info["statistics"])
            self.assertIn("share_count", note_info["statistics"])
            self.assertIn("collected_count", note_info["statistics"])
            
            # 验证作者信息结构
            self.assertIn("id", note_info["author"])
            self.assertIn("nickname", note_info["author"])
            self.assertIn("avatar", note_info["author"])
            
            # 验证媒体信息结构
            self.assertIn("cover_url", note_info["media"])
            self.assertIn("type", note_info["media"])
            
            # 如果是视频类型，验证视频URL
            if note_info["type"] == "video":
                self.assertIn("video_url", note_info["media"])
                self.assertTrue(note_info["media"]["video_url"].startswith("http"))
            
            # 验证时间戳
            self.assertIn("create_time", note_info)
            
            # 验证标签
            self.assertIn("tags", note_info)
            self.assertIsInstance(note_info["tags"], list)
            
            # 打印标签
            if note_info["tags"]:
                print(f"标签: {', '.join(note_info['tags'])}")
            
        except XHSError as e:
            self.fail(f"获取笔记信息失败: {str(e)}")
        except Exception as e:
            self.fail(f"测试过程中出现异常: {str(e)}")
    
    def test_03_get_note_info_with_text_extraction(self):
        """测试获取笔记信息并提取文案"""
        print("\n测试获取笔记信息并提取文案...")
        
        # 获取笔记信息 - 提取文案
        try:
            note_info = self.run_async(
                self.service.get_note_info(TEST_NOTE_URL, extract_text=True)
            )
            
            # 基本验证
            self.assertIsNotNone(note_info)
            
            # 检查是否有文案提取结果
            if note_info["type"] == "video":
                if "transcribed_text" in note_info:
                    print(f"提取的文案: {note_info['transcribed_text'][:100]}..." 
                          if len(note_info.get('transcribed_text', '')) > 100 
                          else note_info.get('transcribed_text', 'None'))
                else:
                    print("警告: 视频未包含提取的文案字段")
            else:
                print(f"笔记类型为 {note_info['type']}，不需要提取文案")
            
        except XHSError as e:
            print(f"警告: 获取笔记信息或提取文案失败: {str(e)}")
            print("这可能是正常的，因为提取文案需要下载视频并处理")
            # 不要将这个作为测试失败，因为文案提取容易受外部因素影响
        except Exception as e:
            self.fail(f"测试过程中出现意外异常: {str(e)}")
    
    def test_04_get_user_info_by_id(self):
        """测试通过ID获取用户信息"""
        print("\n测试通过ID获取用户信息...")
        
        try:
            user_info = self.run_async(
                self.service.get_user_info(TEST_USER_ID)
            )
            
            # 验证用户信息结构
            self.assertIsNotNone(user_info)
            self.assertIn("user_id", user_info)
            self.assertIn("nickname", user_info)
            self.assertIn("avatar", user_info)
            self.assertIn("description", user_info)
            self.assertIn("statistics", user_info)
            
            # 打印基本信息
            print(f"用户ID: {user_info['user_id']}")
            print(f"昵称: {user_info['nickname']}")
            print(f"描述: {user_info['description'][:50]}..." 
                  if len(user_info.get('description', '')) > 50 
                  else user_info.get('description', 'None'))
            
            # 验证统计信息
            self.assertIn("following_count", user_info["statistics"])
            self.assertIn("follower_count", user_info["statistics"])
            
            # 打印统计信息
            print(f"关注数: {user_info['statistics']['following_count']}")
            print(f"粉丝数: {user_info['statistics']['follower_count']}")
            
            # 验证标签
            if "tags" in user_info and user_info["tags"]:
                print(f"标签: {', '.join(user_info['tags'])}")
            
        except XHSError as e:
            self.fail(f"通过ID获取用户信息失败: {str(e)}")
        except Exception as e:
            self.fail(f"测试过程中出现异常: {str(e)}")
    
    def test_05_get_user_info_by_url(self):
        """测试通过URL获取用户信息"""
        print("\n测试通过URL获取用户信息...")
        
        try:
            user_info = self.run_async(
                self.service.get_user_info(TEST_USER_URL)
            )
            
            # 验证用户信息结构
            self.assertIsNotNone(user_info)
            self.assertIn("user_id", user_info)
            self.assertIn("nickname", user_info)
            
            # 打印基本信息
            print(f"用户ID: {user_info['user_id']}")
            print(f"昵称: {user_info['nickname']}")
            
            # 验证是否与通过ID获取的结果匹配
            user_info_by_id = self.run_async(
                self.service.get_user_info(TEST_USER_ID)
            )
            
            # 比较关键字段
            self.assertEqual(user_info.get("nickname"), user_info_by_id.get("nickname"))
            
        except XHSError as e:
            self.fail(f"通过URL获取用户信息失败: {str(e)}")
        except Exception as e:
            self.fail(f"测试过程中出现异常: {str(e)}")
    
    def test_06_error_handling_invalid_url(self):
        """测试错误处理 - 无效URL"""
        print("\n测试错误处理 - 无效URL...")
        
        invalid_url = "https://www.xiaohongshu.com/invalid-url-test"
        
        try:
            # 此处应该抛出XHSError
            _ = self.run_async(
                self.service.get_note_info(invalid_url)
            )
            self.fail("预期应抛出XHSError，但未抛出")
        except XHSError as e:
            # 捕获预期的错误
            print(f"预期错误被捕获: {str(e)}")
            # 测试通过
            pass
        except Exception as e:
            self.fail(f"抛出了意外类型的异常: {type(e).__name__}: {str(e)}")
    
    def test_07_parse_count_string(self):
        """测试数量字符串解析方法"""
        print("\n测试数量字符串解析方法...")
        
        test_cases = [
            ("0", 0),
            ("42", 42),
            ("1.2万", 12000),
            ("5.6万", 56000),
            ("1.2亿", 120000000),
            ("", 0),
            (None, 0),
            ("invalid", 0)
        ]
        
        for input_str, expected in test_cases:
            result = self.service._parse_count_string(input_str)
            self.assertEqual(result, expected, f"解析 '{input_str}' 应得到 {expected}，但得到了 {result}")
            print(f"解析 '{input_str}' => {result} ✓")
    
    def test_08_parse_datetime_string(self):
        """测试日期时间字符串解析方法"""
        print("\n测试日期时间字符串解析方法...")
        
        test_cases = [
            ("2023-05-19 18:08:17", True),
            ("2023/05/19 18:08:17", True),
            ("2023-05-19", True),
            ("2023/05/19", True),
            ("invalid-date", False),
            ("", False),
            (None, False)
        ]
        
        for input_str, should_parse in test_cases:
            result = self.service._parse_datetime_string(input_str)
            if should_parse:
                self.assertGreater(result, 0, f"解析 '{input_str}' 应成功，但返回了 {result}")
                print(f"解析 '{input_str}' => {result} ✓")
            else:
                self.assertEqual(result, 0, f"解析 '{input_str}' 应失败，但返回了 {result}")
                print(f"解析 '{input_str}' => {result} ✓ (预期失败)")
    
    def test_09_cookies_loaded(self):
        """测试Cookie加载情况"""
        print("\n测试Cookie加载情况...")
        
        # 检查是否有Cookie
        if self.service.cookies_str:
            print(f"Cookie已加载: {self.service.cookies_str[:30]}...")
            self.assertTrue(len(self.service.cookies_str) > 10)
        else:
            print("警告: 未加载Cookie，服务可能无法正常工作")
            # 这不应该导致测试失败，因为可能是测试环境配置问题
    
    def test_10_stress_test(self):
        """简单的压力测试 - 连续发起多个请求"""
        print("\n运行简单的压力测试 - 连续发起多个请求...")
        
        # 跳过实际测试以避免API滥用，在需要时取消注释
        print("压力测试已跳过，以避免API滥用。需要时可以取消注释。")
        return
        
        # try:
        #     # 创建多个请求任务
        #     tasks = [
        #         self.service.get_note_info(TEST_NOTE_URL, extract_text=False)
        #         for _ in range(3)
        #     ]
        #     
        #     # 并发执行任务
        #     results = self.run_async(asyncio.gather(*tasks))
        #     
        #     # 验证所有请求都成功
        #     for i, result in enumerate(results):
        #         self.assertIsNotNone(result)
        #         self.assertIn("note_id", result)
        #         print(f"请求 {i+1} 成功")
        #     
        # except Exception as e:
        #     self.fail(f"压力测试失败: {str(e)}")


def print_separator():
    """打印分隔线"""
    print("=" * 70)


def verify_node_modules():
    """验证Node.js模块环境"""
    node_path = os.environ.get("NODE_PATH", "未设置")
    print(f"NODE_PATH: {node_path}")
    
    # 检查目录是否存在
    if node_path != "未设置":
        jsdom_path = os.path.join(node_path, "jsdom")
        if os.path.exists(jsdom_path):
            print(f"✓ jsdom 模块目录存在: {jsdom_path}")
        else:
            print(f"✗ jsdom 模块目录不存在: {jsdom_path}")
    
    # 尝试使用 Node.js 检查模块是否可用
    try:
        import subprocess
        result = subprocess.run(
            ["node", "-e", "try { require('jsdom'); console.log('jsdom module found'); } catch(e) { console.error(e.message); }"],
            capture_output=True, text=True, check=False
        )
        print(f"Node.js 检查结果: {result.stdout or result.stderr}")
    except Exception as e:
        print(f"执行 Node.js 检查时出错: {e}")


if __name__ == "__main__":
    print_separator()
    print("小红书服务测试开始")
    print_separator()
    
    # 检查环境
    print("检查Node.js环境...")
    verify_node_modules()
    print_separator()
    
    # 运行测试
    unittest.main()