select * from log_trace lt 
order by created_at desc 
limit 100;


INSERT INTO meta_app (
    name, 
    domain, 
    public_key, 
    private_key, 
    key_version, 
    status, 
    sign_type, 
    sign_config
) VALUES (
    'test_signature_app', 
    'localhost', 
    'test_public_key', 
    'test_secret_key', 
    1, 
    1, 
    'hmac_sha256', 
    '{"description": "用于验签测试"}'
);



select * from meta_app
WHERE 1=1
-- and name = 'test_signature_app'
AND id = '16dad276-16e3-44d9-aefd-9fbee35ffb0b'
order by created_at desc 
limit 100;









 git push bot-api-v3-github master:main;   

(venv) v9@v9deMacBook-Pro bot-api-v1 % uvicorn bot_api_v1.app.core.app_factory:create_app --reload --host 0.0.0.0 --port 8000



curl -X POST "http://localhost:8000/api/script/transcribe" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -d '{"url": "https://www.youtube.com/shorts/O8GAUEDR0Is"}'


  {
    "version": "0.2.0",
    "configurations": [
      {
        "name": "FastAPI Debug (Async)",
        "type": "debugpy",
        "request": "launch",
        "program": "-m",
        "args": [
          "uvicorn",
          "bot_api_v1.app.core.app_factory:create_app",
          "--reload",
          "--host=0.0.0.0",
          "--port=8000"
        ],
        "env": {
          "PYTHONPATH": "${workspaceFolder}/src"
        },
        "justMyCode": false,
        "console": "integratedTerminal",
        "cwd": "${workspaceFolder}",
        "asyncio": "enabled"  // 关键：启用异步调试支持
      }
    ]
  }


2. 安全模块组织

app/security目录下crypto.py和feishu_sheet_signature.py耦合度较高
建议按功能拆分：
Copyapp/security/
├── crypto/         # 通用加密
│   └── base.py
├── signature/      # 签名验证
│   ├── base.py
│   └── providers/
│       ├── hmac.py
│       ├── rsa.py
│       └── feishu.py
└── encryption/     # 数据加解密
    └── symmetric.py


3. 配置管理

app/core/config.py配置项过于庞大
建议拆分为：
Copyapp/core/config/
├── base.py        # 基础配置
├── database.py    # 数据库配置
├── logging.py     # 日志配置
└── security.py    # 安全配置


4. 测试组织

tests目录测试文件组织不够清晰
建议按模块对应测试：
Copytests/
├── unit/
│   ├── test_security.py
│   ├── test_services.py
│   └── test_models.py
├── integration/
│   └── test_api_workflows.py
└── performance/
    └── test_signature_performance.py


5. 异常处理

缺少统一的异常基类和异常管理
建议增加 app/exceptions/ 目录，定义通用异常类型

6. 常量管理

建议增加 app/constants/ 目录，集中管理常量
Copyapp/constants/
├── auth.py        # 认证相关常量
├── log_levels.py  # 日志级别
└── system.py      # 系统常量


app/security/
├── crypto/         # 通用加密
│   └── base.py
├── signature/      # 签名验证
│   ├── base.py
│   └── providers/
│       ├── hmac.py
│       ├── rsa.py
│       └── feishu.py
└── encryption/     # 数据加解密
    └── symmetric.py