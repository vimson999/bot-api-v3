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


curl -X GET "http://localhost:8000/api/health"\
  -H "Content-Type: application/json" \
  -H "x-source: v9-mac-book" \
  -H "x-app-id: local-test" \
  -H "x-user-uuid: user-v999" \
  -H "x-user-nickname: 你说呢" \

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



待改进点
2.1 安全模块(security)
Copysecurity/
├── crypto/
│   ├── __init__.py
│   └── base.py
├── signature/
│   ├── base.py
│   └── providers/
│       ├── hmac.py
│       ├── rsa.py
│       └── feishu.py
└── encryption/
    └── symmetric.py
2.2 配置管理(core/config)
Copyconfig/
├── base.py        # 基础配置
├── database.py    # 数据库配置
├── logging.py     # 日志配置
└── security.py    # 安全配置
2.3 异常处理
建议增加 app/exceptions/ 目录
Copyexceptions/
├── base.py        # 基础异常类
├── auth.py        # 认证相关异常
├── database.py    # 数据库异常
└── validation.py  # 数据验证异常
2.4 常量管理
Copyconstants/
├── auth.py        # 认证相关常量
├── log_levels.py  # 日志级别
└── system.py      # 系统常量
3. 代码质量问题
3.1 依赖管理

检查 requirements.txt 是否有过时依赖
考虑使用 poetry 或 pipenv 进行依赖管理
区分开发依赖和生产依赖

3.2 性能和安全

日志脱敏
异常处理统一
敏感信息加密存储
并发控制
请求限流

4. 建议的重构方向
4.1 模块解耦

降低模块间耦合度
使用依赖注入
遵循依赖倒置原则

4.2 可观测性

增加链路追踪
完善监控
性能埋点

4.3 代码规范

统一错误处理
日志规范化
类型注解完善
Docstring 规范

5. 测试策略优化
Copytests/
├── unit/           # 单元测试
│   ├── test_crypto.py
│   ├── test_services.py
│   └── test_models.py
├── integration/    # 集成测试
│   └── test_api_workflows.py
└── performance/    # 性能测试
    └── test_signature_performance.py
6. 具体重构建议
6.1 依赖注入容器
考虑使用 dependency_injector 库管理依赖
6.2 配置管理

使用 pydantic 进行配置验证
支持多环境配置
环境变量优先级

6.3 日志系统

使用结构化日志
支持多handler
日志级别灵活配置




import { basekit, FieldType, field, FieldComponent, FieldCode,AuthorizationType } from '@lark-opdev/block-basekit-server-api';
const { t } = field;

// 通过addDomainList添加请求接口的域名
basekit.addDomainList(['127.0.0.1']);

basekit.addField({
  options: {
    disableAutoUpdate: true, // 关闭自动更新
  },
  formItems: [
    {
      key: 'url',
      label: '视频地址',
      component: FieldComponent.FieldSelect,
      props: {
        supportType: [FieldType.Text],
      },
      validator: {
        required: true,
      }
    },
  ],
  // 定义捷径的返回结果类型
  resultType: {
    type: FieldType.Object,
    extra: {
      icon: {
        light: 'https://lf3-static.bytednsdoc.com/obj/eden-cn/eqgeh7upeubqnulog/chatbot.svg',
      },
      properties: [
        {
          key: 'id',
          isGroupByKey: true,
          type: FieldType.Text,
          title: 'id',
          hidden: true,
        },
        {
          key: 'content',
          type: FieldType.Text,
          title: '文案',
          primary: true,
        },
        {
          key: 'title',
          type: FieldType.Text,
          title: '标题',
        },
      ],
    },
  },
  authorizations: [
    {
      id: 'auth_key',// 授权的id，用于context.fetch第三个参数以区分该请求使用哪个授权
      platform: 'baidu',// 需要与之授权的平台,比如baidu(必须要是已经支持的三方凭证,不可随便填写,如果想要支持更多的凭证，请填写申请表单)
      type: AuthorizationType.HeaderBearerToken,
      required: true,// 设置为选填，用户如果填了授权信息，请求中则会携带授权信息，否则不带授权信息
      instructionsUrl: "https://www.feishu.com",// 帮助链接，告诉使用者如何填写这个apikey
      label: '测试授权',
      icon: {
        light: '',
        dark: ''
      }
    }
  ],
  execute: async (formItemParams, context) => {
    // 获取字段值时需要正确处理字段结构
    const urlField = formItemParams.url;
    
    // 检查字段存在性
    if (!urlField || !urlField.length) {
      return {
        code: FieldCode.ConfigError,
        msg: '请先选择视频地址字段',
      };
    }
    
    // 从文本字段中提取实际的URL文本
    let urlText = '';
    for (const item of urlField) {
      if (item.type === 'text') {
        urlText += item.text;
      } else if (item.type === 'url') {
        urlText += item.link;
      }
    }
    
    if (!urlText) {
      return {
        code: FieldCode.ConfigError,
        msg: '未能从所选字段中提取有效的URL',
      };
    }

    console.log('从字段中提取的URL:', urlText);

    try {
      const host_url = 'http://127.0.0.1:8000/api/script/transcribe';
      
      // 使用类型断言获取 baseSignature 和 packID
      const baseSignature = (context as any).baseSignature;
      const packID = (context as any).packID;
      
      console.log('流量标识信息:', {
        baseSignature,
        packID
      });
      
      const response = await context.fetch(host_url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-source': 'feishu-sheet',
          'x-app-id': 'sheet-api',
          'x-user-uuid': 'user-123456',
          // 'x-user-nickname': '晓山',
          'x-base-signature': baseSignature,
          'x-pack-id': packID
        },
        body: JSON.stringify({ url: urlText }),
      }, 'auth_key');
      
      const res = await response.json();
      console.log('API响应:', res);

      // 检查响应是否成功，并从正确的路径提取数据
      if (res.code === 200 && res.data) {
        return {
          code: FieldCode.Success,
          data: {
            id: `${Date.now()}`,
            content: res.data.text || '无内容',
            title: res.data.title || '无标题',
          },
        };
      } else {
        return {
          code: FieldCode.Error,
          msg: `API响应错误: ${res.message || '未知错误'}`,
        };
      }
    } catch (e) {
      console.error('请求失败:', e);
      return {
        code: FieldCode.Error,
        msg: `请求失败: ${e.message}`
      };
    }
  },
});

export default basekit;



{
    "authorizations": [
        {
            "auth_key": ["your-api-key-here"]
        }
    ]
}


https://ycn0x2weafez.feishu.cn/base/QJzUb6WtzaAnXWs4m35cI5tEn3f?table=tblF20SrgIMNqrI3&view=vewPbLApNL

https://feishu.feishu.cn/docx/SZFpd9v6EoHMI7xEhWhckLLfnBh
git push https://vim999:e41eeb6d5f1fb9dc20c72c374eaff93a@gitee.com/vim999/bot_api_v1.git master

debug_pack_id_1742102777762




git pull origin master

# 配置pip使用清华大学镜像
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip install --upgrade pip
pip install -r requirements.txt

# 在项目根目录创建.env文件
echo "DATABASE_URL=postgresql+asyncpg://cappa_rw:RWcappaDb!!!2025@10.0.16.12:5432/cappadocia_v1" > .env
echo 'DATABASE_URL=postgresql+asyncpg://cappa_rw:RWcappaDb!!!2025@10.0.16.12:5432/cappa_p_v1' > .env

# 确保你在项目目录中
cd /code/bot_api
# 设置Python路径
export PYTHONPATH=$PWD/src:$PYTHONPATH

uvicorn bot_api_v1.app.core.app_factory:create_app --host 0.0.0.0 --port 8000
nohup uvicorn bot_api_v1.app.core.app_factory:create_app --host 0.0.0.0 --port 8000 > api.log 2>&1 &

# 创建systemd服务文件
sudo nano /etc/systemd/system/bot_api.service

添加以下内容（注意替换用户名和路径）：
[Unit]
Description=Bot API Service
After=network.target

[Service]
User=lighthouse
Group=lighthouse
WorkingDirectory=/code/bot_api
Environment="PATH=/code/bot_api/venv/bin"
Environment="PYTHONPATH=/code/bot_api/src"
-- ExecStart=/code/bot_api/venv/bin/uvicorn bot_api_v1.app.core.app_factory:create_app --host 0.0.0.0 --port 8000
ExecStart=/code/bot_api/venv/bin/gunicorn bot_api_v1.app.core.app_factory:create_app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

然后启用并启动服务：
sudo systemctl daemon-reload
sudo systemctl enable bot_api
sudo systemctl start bot_api

检查服务状态：
sudo systemctl status bot_api


重启服务
sudo systemctl restart bot_api


sudo apt update
sudo apt install ffmpeg -y

# 拉取最新代码
cd /code/bot_api
git pull

# 安装新的依赖（如果有）
source venv/bin/activate
pip install -r requirements.txt

# 重启服务
sudo systemctl restart bot_api



sudo apt update
sudo apt install ffmpeg -y


查看服务状态：sudo systemctl status bot_api
重启服务：sudo systemctl restart bot_api
停止服务：sudo systemctl stop bot_api
启动服务：sudo systemctl start bot_api
查看服务日志：sudo journalctl -u bot_api -f




curl -X GET "http://101.35.56.140:8000/api/health" \
  -H "Content-Type: application/json" \
  -H "x-source: test" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user"



curl -X GET "http://101.35.56.140/api/health" \
  -H "Content-Type: application/json" \
  -H "x-source: test" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user"



curl -X POST "http://101.35.56.140:8000/api/script/transcribe" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -H "Authorization: test-auth-key-123456" \
  -H "x-base-signature: eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoiZGVidWdfcGFja19pZF8xNzQyMTAyNzc3NzYyIiwiZXhwIjoxNzQyMjAwNDk5NDMwfQ==.jR1ZTNdWSUzQXmVa5sR9P-pb20PxSXNeO_3VRvhjC_49lBGN25QQYn_XNIvYaiSESZDyO24U_nLBwehJGc7TDATMnrkgeTi3tr5aA-4L_EqAXZpKGufVIdUIVxYkcXdK8E-AJB_CoNSrmczNC0BbxVdyDUzN1zyIpL5paFcDe3Zi29--OlbsBGijP6OhXeeWO8tc8qFAE6PhYdwpcNKEBiZnDFEdCpFZO2oyAiLWUQm1D030Ki0SNQybVIdHIfDzotv7nfzrLQTPdQfWKKUTdS4tqR__giiPxojslSCMcQHf9BBTYaZKoCpMj77DUoOWLiOHkSJCOpyPAROmsduvVQ==" \
  -d '{"url": "https://www.youtube.com/shorts/O8GAUEDR0Is"}'




curl -X POST "http://101.35.56.140/api/script/transcribe" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -H "Authorization: test-auth-key-123456" \
  -H "x-base-signature: eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoiZGVidWdfcGFja19pZF8xNzQyMTAyNzc3NzYyIiwiZXhwIjoxNzQyMjAwNDk5NDMwfQ==.jR1ZTNdWSUzQXmVa5sR9P-pb20PxSXNeO_3VRvhjC_49lBGN25QQYn_XNIvYaiSESZDyO24U_nLBwehJGc7TDATMnrkgeTi3tr5aA-4L_EqAXZpKGufVIdUIVxYkcXdK8E-AJB_CoNSrmczNC0BbxVdyDUzN1zyIpL5paFcDe3Zi29--OlbsBGijP6OhXeeWO8tc8qFAE6PhYdwpcNKEBiZnDFEdCpFZO2oyAiLWUQm1D030Ki0SNQybVIdHIfDzotv7nfzrLQTPdQfWKKUTdS4tqR__giiPxojslSCMcQHf9BBTYaZKoCpMj77DUoOWLiOHkSJCOpyPAROmsduvVQ==" \
  -d '{"url": "https://www.bilibili.com/video/BV17eQNY2Eem?spm_id_from=333.1007.tianma.1-3-3.click"}'



curl -X POST "http://101.35.56.140:8000/api/script/transcribe" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -H "Authorization: test-auth-key-123456" \
  -H "x-base-signature: eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoiZGVidWdfcGFja19pZF8xNzQyMTAyNzc3NzYyIiwiZXhwIjoxNzQyMjAwNDk5NDMwfQ==.jR1ZTNdWSUzQXmVa5sR9P-pb20PxSXNeO_3VRvhjC_49lBGN25QQYn_XNIvYaiSESZDyO24U_nLBwehJGc7TDATMnrkgeTi3tr5aA-4L_EqAXZpKGufVIdUIVxYkcXdK8E-AJB_CoNSrmczNC0BbxVdyDUzN1zyIpL5paFcDe3Zi29--OlbsBGijP6OhXeeWO8tc8qFAE6PhYdwpcNKEBiZnDFEdCpFZO2oyAiLWUQm1D030Ki0SNQybVIdHIfDzotv7nfzrLQTPdQfWKKUTdS4tqR__giiPxojslSCMcQHf9BBTYaZKoCpMj77DUoOWLiOHkSJCOpyPAROmsduvVQ==" \
  -d '{"url": "https://www.bilibili.com/video/BV17eQNY2Eem?spm_id_from=333.1007.tianma.1-3-3.click"}'



curl -X POST "http://localhost:8000/api/script/transcribe" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -H "Authorization: test-auth-key-123456" \
  -H "x-base-signature: eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoiZGVidWdfcGFja19pZF8xNzQyMTAyNzc3NzYyIiwiZXhwIjoxNzQyMjAwNDk5NDMwfQ==.jR1ZTNdWSUzQXmVa5sR9P-pb20PxSXNeO_3VRvhjC_49lBGN25QQYn_XNIvYaiSESZDyO24U_nLBwehJGc7TDATMnrkgeTi3tr5aA-4L_EqAXZpKGufVIdUIVxYkcXdK8E-AJB_CoNSrmczNC0BbxVdyDUzN1zyIpL5paFcDe3Zi29--OlbsBGijP6OhXeeWO8tc8qFAE6PhYdwpcNKEBiZnDFEdCpFZO2oyAiLWUQm1D030Ki0SNQybVIdHIfDzotv7nfzrLQTPdQfWKKUTdS4tqR__giiPxojslSCMcQHf9BBTYaZKoCpMj77DUoOWLiOHkSJCOpyPAROmsduvVQ==" \
  -d '{"url": "https://www.bilibili.com/video/BV17eQNY2Eem?spm_id_from=333.1007.tianma.1-3-3.click"}'


是的，你目前的部署方式已经达到了基础的生产级别部署标准。通过使用systemd服务，你已经实现了几个重要的生产环境需求：

服务持久化运行 - 应用作为systemd服务运行，即使在SSH会话结束后仍能继续运行
自动重启 - 如果应用崩溃，systemd会自动重启它
开机自启 - 服务器重启后，应用会自动启动
日志管理 - systemd提供集中化的日志管理

不过，如果要达到完整的生产级别部署，你可能m还需要考虑以下几个方面：

HTTPS支持 - 通过Nginx或类似工具实现HTTPS和反向代理
备份策略 - 定期备份数据库和关键配置

负载均衡 - 如果预期有大量流量，添加负载均衡器
监控 - 添加如Prometheus+Grafana的监控系统
CI/CD - 实现自动化部署流程
更完善的日志管理 - 例如ELK栈或类似工具
环境隔离 - 完全分离开发、测试和生产环境




配置nginx
sudo nano /etc/nginx/sites-available/bot_api
sudo ln -s /etc/nginx/sites-available/bot_api /etc/nginx/sites-enabled/
sudo nginx -t  # 检查语法
sudo systemctl restart nginx





crontab -e
0 3 * * * /code/bot_api/src/bot_api_v1/scripts/backup_db.sh >> /var/log/db_backups.log 2>&1
crontab -l


sudo touch /var/log/db_backups.log
sudo chown lighthouse:lighthouse /var/log/db_backups.log


查看服务是否在运行以及有无错误消息。如果服务已经崩溃，请查看日志以获取更多信息：
sudo journalctl -u bot_api -n 25 --no-pager



 tree -L 7 -I 'venv'



 curl -X POST "http://localhost:8000/api/douyin/video/info" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -H "Authorization: test-auth-key-123456" \
  -H "x-base-signature: eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoiZGVidWdfcGFja19pZF8xNzQyMTAyNzc3NzYyIiwiZXhwIjoxNzQyMjAwNDk5NDMwfQ==.jR1ZTNdWSUzQXmVa5sR9P-pb20PxSXNeO_3VRvhjC_49lBGN25QQYn_XNIvYaiSESZDyO24U_nLBwehJGc7TDATMnrkgeTi3tr5aA-4L_EqAXZpKGufVIdUIVxYkcXdK8E-AJB_CoNSrmczNC0BbxVdyDUzN1zyIpL5paFcDe3Zi29--OlbsBGijP6OhXeeWO8tc8qFAE6PhYdwpcNKEBiZnDFEdCpFZO2oyAiLWUQm1D030Ki0SNQybVIdHIfDzotv7nfzrLQTPdQfWKKUTdS4tqR__giiPxojslSCMcQHf9BBTYaZKoCpMj77DUoOWLiOHkSJCOpyPAROmsduvVQ==" \
  -d '{"url": "https://v.douyin.com/i53yJjA3/", "extract_text": false}'

# 2. 测试抖音视频信息API (提取文案)
curl -X POST "http://localhost:8000/api/douyin/video/info" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -H "Authorization: test-auth-key-123456" \
  -H "x-base-signature: eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoiZGVidWdfcGFja19pZF8xNzQyMTAyNzc3NzYyIiwiZXhwIjoxNzQyMjAwNDk5NDMwfQ==.jR1ZTNdWSUzQXmVa5sR9P-pb20PxSXNeO_3VRvhjC_49lBGN25QQYn_XNIvYaiSESZDyO24U_nLBwehJGc7TDATMnrkgeTi3tr5aA-4L_EqAXZpKGufVIdUIVxYkcXdK8E-AJB_CoNSrmczNC0BbxVdyDUzN1zyIpL5paFcDe3Zi29--OlbsBGijP6OhXeeWO8tc8qFAE6PhYdwpcNKEBiZnDFEdCpFZO2oyAiLWUQm1D030Ki0SNQybVIdHIfDzotv7nfzrLQTPdQfWKKUTdS4tqR__giiPxojslSCMcQHf9BBTYaZKoCpMj77DUoOWLiOHkSJCOpyPAROmsduvVQ==" \
  -d '{"url": "https://v.douyin.com/i53yJjA3/", "extract_text": true}'



curl -X POST "http://localhost:8000/api/douyin/user/info" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -H "Authorization: test-auth-key-123456" \
  -H "x-base-signature: eyJzb3VyY2UiOiJiYXNlIiwidmVyc2lvbiI6InYxIiwicGFja0lEIjoiZGVidWdfcGFja19pZF8xNzQyMTAyNzc3NzYyIiwiZXhwIjoxNzQyMjAwNDk5NDMwfQ==.jR1ZTNdWSUzQXmVa5sR9P-pb20PxSXNeO_3VRvhjC_49lBGN25QQYn_XNIvYaiSESZDyO24U_nLBwehJGc7TDATMnrkgeTi3tr5aA-4L_EqAXZpKGufVIdUIVxYkcXdK8E-AJB_CoNSrmczNC0BbxVdyDUzN1zyIpL5paFcDe3Zi29--OlbsBGijP6OhXeeWO8tc8qFAE6PhYdwpcNKEBiZnDFEdCpFZO2oyAiLWUQm1D030Ki0SNQybVIdHIfDzotv7nfzrLQTPdQfWKKUTdS4tqR__giiPxojslSCMcQHf9BBTYaZKoCpMj77DUoOWLiOHkSJCOpyPAROmsduvVQ==" \
  -d '{"user_id": "MS4wLjABAAAAFec6xaVDCLvpqpB-Vd4_qsTgwFlJM1Y2r_ZSoFGHRG8t7wa1vCK1tDnmL_s22_mD"}'





curl -X POST "http://localhost:8000/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.douyin.com/video/7475254041207950642", "extract_text": true}'




curl -X POST "http://localhost:8000/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.xiaohongshu.com/explore/67cc347d000000000602a583?xsec_token=ABgdCG8TSk2e_lpVMi49OnDlhTot4KcZMDAoAR2YQfD0A=&xsec_source=pc_feed", "extract_text": true}'





# 在您的项目根目录执行
mkdir -p src/bot_api_v1/libs
git submodule add https://github.com/vimson999/Spider_XHS.git src/bot_api_v1/libs/spider_xhs
git submodule update --init --recursive



cat src/bot_api_v1/libs/spider_xhs/requirements.txt >> requirements.txt
pip install -r requirements.txt

cd src/bot_api_v1/libs/spider_xhs
npm install