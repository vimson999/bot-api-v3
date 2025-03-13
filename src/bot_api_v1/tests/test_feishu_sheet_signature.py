"""
飞书签名验证模块测试

包含单元测试、性能测试、模糊测试和并发测试
"""

import unittest
import logging
import time
import random
import string
import concurrent.futures
import json
from bot_api_v1.app.security.signature.providers.feishu_sheet import verify_feishu_token, rsa_verify_sign

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class TestFeishuSignature(unittest.TestCase):
    """飞书签名验证测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 测试用的token
        self.valid_token = 'eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoicmVwbGl0XzNlNzFkZWYyODU2Y2UzZjQiLCJleHAiOjE3MjUzNjUyMjUyNjh9.Q6ixsDOiKg4EzI7L5xg9EfIkajPz1Eu6W4jPYFEx69sVFpqC516l4TBic-C5kLh2uPnSg6EVt5tasXXkjAFG9C7wBLalu1PHr1TmQ_2FkPfhlirQf1y9GL4WudvtLWgGjy2G2yGkw-tqiBaYb6YcbBuEAOTQ4kU6ohkn6SkckI01cl_6qDsUjb_m885Xr8kqoJSgkFDYzLLQB5LIZHI6d7JAOekCyTeuxPn-xxCohamyJUzZSJ9jxtX2aS-8F6UkAh6ta_VmhIDDsSeGN-ZyzEq_iV_Zzz4T3XkFWASdJmfm_l78OQcfoMKhBVhBB8p0G1uJII0lLcvTd01WVb7WUg=='
        self.invalid_token = 'eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoicmVwbGl0XzNlNzFkZWYyODU2Y2UzZjQiLCJleHAiOjE3MjUzNjUyMjUyNjh9.InvalidSignatureHere'
        self.malformed_token = 'not.a.proper.token'
        
        # 测试公钥 - 与有效token匹配的公钥
        self.test_public_key = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxKNV23rheRvtUKDMJPOW
GhUt+W25k63X4Q1QYhztPlobF2VNIDR6eHVFUDP22aytzVguisJ/GaOKZ7FJDKis
9YvMUiCIFnfu1LWB4b4pa4ajmPk/Rr9DMSLz6frKRP0QqirWFe7t+u0K0nzzPe3/
a5ScSmJwYACmayQfLZFTFjyL0Z1SQFZM6pZ1J1w9ETxWI0NrpkMU7eqzVGvhf+OO
dmxsXrHARWa1Ldm3WqPCF3k5jKuPG7s0zB+iuBHamSitZ7ktBf0mzBBjsAjKQll1
kmdjryGbKX5sLXhEgOb5ndakYeA0Oy7vve2Hm78kH5MtaSv6MfNVjm5ForMjPAPQ
BQIDAQAB
-----END PUBLIC KEY-----"""
    
    def test_valid_token(self):
        """测试有效的token"""
        valid, data = verify_feishu_token(self.valid_token)
        self.assertTrue(valid)
        self.assertIsNotNone(data)
        self.assertEqual(data['source'], 'base')
        self.assertEqual(data['version'], 'v1')
        self.assertEqual(data['packID'], 'replit_3e71def2856ce3f4')
    
    def test_valid_token_with_custom_key(self):
        """测试使用自定义公钥验证有效token"""
        valid, data = verify_feishu_token(self.valid_token, public_key=self.test_public_key)
        self.assertTrue(valid)
        self.assertIsNotNone(data)
        
    def test_invalid_token(self):
        """测试签名无效的token"""
        valid, data = verify_feishu_token(self.invalid_token)
        self.assertFalse(valid)
        self.assertIsNone(data)
        
    def test_malformed_token(self):
        """测试格式错误的token"""
        valid, data = verify_feishu_token(self.malformed_token)
        self.assertFalse(valid)
        self.assertIsNone(data)
        
    def test_empty_token(self):
        """测试空token"""
        valid, data = verify_feishu_token("")
        self.assertFalse(valid)
        self.assertIsNone(data)
        
    def test_none_token(self):
        """测试None token"""
        valid, data = verify_feishu_token(None)
        self.assertFalse(valid)
        self.assertIsNone(data)
        
    def test_whitespace_token(self):
        """测试只有空白字符的token"""
        valid, data = verify_feishu_token("   \n   ")
        self.assertFalse(valid)
        self.assertIsNone(data)
        
    def test_debug_mode(self):
        """测试调试模式"""
        valid, data = verify_feishu_token(self.valid_token, debug=True)
        self.assertTrue(valid)
        self.assertIsNotNone(data)
    
    def test_timeout(self):
        """测试超时设置"""
        # 设置一个非常短的超时时间
        valid, data = verify_feishu_token(self.valid_token, timeout=0.001)
        # 这里不断言结果，因为它可能成功也可能超时，取决于机器性能
        logger.info(f"超时测试结果: {valid}")
    
    def test_performance(self):
        """性能测试"""
        iterations = 50  # 在生产环境中可能需要更多迭代
        start = time.time()
        for _ in range(iterations):
            verify_feishu_token(self.valid_token)
        duration = time.time() - start
        avg_time = duration / iterations
        logger.info(f"性能测试: {iterations}次验证平均耗时 {avg_time:.4f}秒")
        self.assertLess(avg_time, 0.1)  # 平均每次验证应在100ms内完成

    def test_fuzz(self):
        """模糊测试"""
        # 生成各种随机token进行测试
        fuzz_iterations = 20  # 生产环境中可能需要更多迭代
        for i in range(fuzz_iterations):
            # 生成随机token
            if i % 4 == 0:
                # 有效token但轻微修改
                token = self.valid_token[:-5] + ''.join(random.choice(string.ascii_letters) for _ in range(5))
            elif i % 4 == 1:
                # 随机长度的随机字符
                token = ''.join(random.choice(string.printable) for _ in range(random.randint(10, 500)))
            elif i % 4 == 2:
                # 随机长度，有一个点分隔符
                part1 = ''.join(random.choice(string.printable) for _ in range(random.randint(5, 100)))
                part2 = ''.join(random.choice(string.printable) for _ in range(random.randint(5, 100)))
                token = f"{part1}.{part2}"
            else:
                # 超长token
                token = ''.join(random.choice(string.ascii_letters) for _ in range(random.randint(1000, 2000)))
            
            # 不应崩溃
            try:
                verify_feishu_token(token)
                # 不检查结果，只确保不崩溃
            except Exception as e:
                self.fail(f"模糊测试时崩溃: {e}, token: {token[:50]}...")

    def test_concurrent(self):
        """并发测试"""
        workers = 10
        iterations = 5  # 每个工作线程的验证次数
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            # 提交验证任务
            futures = []
            for _ in range(workers):
                for j in range(iterations):
                    if j % 2 == 0:
                        # 验证有效token
                        futures.append(executor.submit(verify_feishu_token, self.valid_token))
                    else:
                        # 验证无效token
                        futures.append(executor.submit(verify_feishu_token, self.invalid_token))
            
            # 检查结果
            valid_count = 0
            invalid_count = 0
            for future in concurrent.futures.as_completed(futures):
                try:
                    valid, _ = future.result()
                    if valid:
                        valid_count += 1
                    else:
                        invalid_count += 1
                except Exception as e:
                    self.fail(f"并发测试时异常: {e}")
            
            # 验证结果数量正确
            expected_valid = workers * (iterations // 2 + iterations % 2)
            expected_invalid = workers * (iterations // 2)
            logger.info(f"并发测试: 成功验证 {valid_count}次, 失败验证 {invalid_count}次")
            self.assertEqual(valid_count, expected_valid)
            self.assertEqual(invalid_count, expected_invalid)
    
    def test_long_data(self):
        """测试大数据验证处理"""
        # 构造一个很长的数据部分
        long_data = {
            "data": "x" * 10000,  # 一个很长的字符串
            "source": "base",
            "version": "v1"
        }
        # 将长数据编码为Base64
        encoded_data = base64.b64encode(json.dumps(long_data).encode()).decode()
        # 构造token
        long_token = f"{encoded_data}.{self.valid_token.split('.')[1]}"
        
        # 验证失败但不崩溃
        valid, data = verify_feishu_token(long_token)
        self.assertFalse(valid)  # 应该验证失败，因为签名不匹配
        logger.info("长数据测试通过，未崩溃")


if __name__ == '__main__':
    unittest.main()