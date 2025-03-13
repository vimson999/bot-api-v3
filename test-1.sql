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




作为资深研发测试专家，我对项目结构和文件命名有几点观察：
不合理的文件命名或位置

一致性问题：

app/core/service_decorators.py 与其他装饰器文件分开，应该与 app/utils/decorators/gate_keeper.py 放在同一目录下
app/middlewares/logging_middleware.py 名称使用了下划线，而项目其他地方更多使用驼峰或纯小写命名


位置不合理：

app/api/system.py 单独存在，而其他API路由都在 app/api/routers 目录下，应该移到routers下保持一致
app/services/script_service.py 包含具体业务逻辑，但项目没有清晰区分业务服务层


命名混乱：

app/db/session.py 和 app/core/dependencies.py 都定义了获取数据库会话的函数，导致功能重复
app/core/app.py 命名过于宽泛，不能清楚表达其作为应用程序入口点的功能


结构问题：

app/security 目录下的加密相关文件与安全签名验证混在一起，可以进一步分类
app/tasks/base.py 承担了太多职责，应该拆分为更小的模块


缺失的组织：

没有专门的 exceptions 目录来管理自定义异常类
没有统一的 constants 或 config 目录来管理常量和配置


测试文件组织：

tests 目录下文件组织不完善，没有按照应用结构划分测试类别
测试文件命名不一致，有些以 test_ 开头，有些没有


脚本文件混杂：

scripts 目录下的文件混合了多种不同用途的脚本，应该按功能分类