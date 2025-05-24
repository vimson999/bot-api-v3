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


curl -X GET "http://localhost:8083/api/health"\
  -H "Content-Type: application/json" \
  -H "x-source: v9-mac-book" \
  -H "x-app-id: local-test" \
  -H "x-user-uuid: user-v999" \
  -H "x-user-nickname: 你说呢" \

  curl -X GET "http://localhost:8000/api/health"\
  -H "Content-Type: application/json" \
  -H "x-source: v9-mac-book" \
  -H "x-app-id: local-test" \
  -H "x-user-uuid: user-v999" \
  -H "x-user-nickname: 你说呢"



  curl -X GET "http://localhost:8000/api/media/dc/"\
  -H "Content-Type: application/json" \-
  -H "x-source: v9-mac-book" \
  -H "x-app-id: local-test" \
  -H "x-user-uuid: user-v999" \
  -H "x-user-nickname: 你说呢"



  curl -X GET "http://42.192.40.44/api/health"\
  -H "Content-Type: application/json" \
  -H "x-source: v9-mac-book" \
  -H "x-app-id: local-test" \
  -H "x-user-uuid: user-v999" \
  -H "x-user-nickname: 你说呢"

  curl -X GET "http://www.xiaoshanqing.tech/api/health"\
  -H "Content-Type: application/json" \
  -H "x-source: v9-mac-book" \
  -H "x-app-id: local-test" \
  -H "x-user-uuid: user-v999" \
  -H "x-user-nickname: 你说呢"



  curl -X GET "http://localhost:8000/api/test"\
  -H "Content-Type: application/json" \
  -H "x-source: v9-mac-book" \
  -H "x-app-id: local-test" \
  -H "x-user-uuid: user-v999" \
  -H "x-user-nickname: 你说呢"

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

nohup pip install -r requirements.txt > install.log 2>&1 &
tail -f install.log


pip install --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt



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



 tree -L 10 -I 'venv|__pycache__|node_modules|.git|.idea|.vscode|static|dist|logs|tmp|.env|docs'



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



curl -X GET "http://localhost:8083/api/media/test/xhs_sync?extract_text=true" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Key: your_auth_key_here"


curl -X POST "http://www.xiaoshanqing.tech/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.douyin.com/video/7475254041207950642", "extract_text": true}'



curl -X POST "http://121.4.126.31/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.douyin.com/video/7475254041207950642", "extract_text": true}'


curl -X POST "https://121.4.126.31/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.douyin.com/video/7475254041207950642", "extract_text": true}'




curl -X POST "https://www.xiaoshanqing.tech/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.douyin.com/video/7475254041207950642", "extract_text": true}'



curl -X POST "http://127.0.0.1:8083/api/media/dc?url=https://www.kuaishou.com/f/X-6tJ5drN7B0eeHD"
curl -X POST "http://42.192.40.44/api/media/dc?url=https://www.kuaishou.com/f/X-6tJ5drN7B0eeHD"


curl -X POST "http://localhost:8000/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.xiaohongshu.com/explore/67cc347d000000000602a583?xsec_token=ABgdCG8TSk2e_lpVMi49OnDlhTot4KcZMDAoAR2YQfD0A=&xsec_source=pc_feed", "extract_text": true}'



curl -X POST "http://localhost:8000/api/media/extract" \
  -H "Content-Type: application/json" \
  -H "x-source: test-client" \
  -H "x-app-id: test-app" \
  -H "x-user-uuid: test-user" \
  -d '{"url": "https://www.xiaohongshu.com/explore/64674a91000000001301762e?xsec_token=ABAJcy_294mBZauFhAac6izmJvYB6yqm49MAtXSVU8XA4=&xsec_source=pc_feed", "extract_text": true}'





# 在您的项目根目录执行
mkdir -p src/bot_api_v1/libs
git submodule add https://github.com/vimson999/Spider_XHS.git src/bot_api_v1/libs/spider_xhs
git submodule update --init --recursive


cat src/bot_api_v1/libs/spider_xhs/requirements.txt >> requirements.txt
pip install -r requirements.txt

cd src/bot_api_v1/libs/spider_xhs
npm install
npm install jsdom --save

？的bug
需要注意npm nodejs的版本要大于18

TypeError: Cannot read properties of undefined (reading 'call')



git submodule add https://github.com/vimson999/TikTokDownloader.git src/bot_api_v1/libs/tiktok_downloader
git submodule update --init --recursive

cat src/bot_api_v1/libs/tiktok_downloader/requirements.txt >> requirements.txt
pip install -r requirements.txt

pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt


nohup pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt > install.log 2>&1 &
tail -f install.log

pip install -r src/bot_api_v1/libs/spider_xhs/requirements.txt
pip install -r src/bot_api_v1/libs/tiktok_downloader/requirements.txt


https://www.douyin.com/video/7475254041207950642
https://www.xiaohongshu.com/explore/67e2b3f900000000030286ce?xsec_token=ABsttmnMANeopanZhB7mwrTWl3izLUb0_nFBSUxqS4EZk=&xsec_source=pc_feed



export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export CT2_NUM_THREADS=1 # 这个也加上，以覆盖 CTranslate2 可能的默认设置
echo "OMP_NUM_THREADS 已设置为: $OMP_NUM_THREADS" # 确认设置成功


celery -A bot_api_v1.app.tasks.celery_app worker --loglevel=info
# 在 src 目录下运行
# 在 src 目录下
celery -A bot_api_v1.app.tasks.celery_app worker --loglevel=info -Q celery,media_extraction
# 同样在 src 目录下
celery -A bot_api_v1.app.tasks.celery_app flower --port=5555
http://localhost:5555

export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8


# Celery (覆盖默认值或确认值)
# CELERY_BROKER_URL="redis://:login4RDS!!!@101.35.56.140:6379/0"
# CELERY_RESULT_BACKEND="redis://:login4RDS!!!@101.35.56.140:6379/1"



在启动 Worker 前设置环境变量 (指向本地开发环境):
打开运行 Celery Worker 的终端。
确保你在 src 目录下。
执行以下 export 命令（确保你的 Shell 支持 export，如果是 Windows cmd 可能需要用 set）：


export CELERY_BROKER_URL='redis://localhost:6379/0' 
export CELERY_RESULT_BACKEND='redis://localhost:6379/1' 
export CACHE_REDIS_URL='redis://localhost:6379/2' 


git push https://vim999:b5ff334e279b324f74a78c9d5d67c046@gitee.com/vim999/bot_api_v1.git master



celery -A bot_api_v1.app.tasks.celery_app worker --loglevel=debug -Q celery,media_extraction -P solo -n task_A
celery -A bot_api_v1.app.tasks.celery_app worker --loglevel=debug -Q transcription -P solo -n task_B
celery -A bot_api_v1.app.tasks.celery_app worker --loglevel=debug -Q logging  -P solo -n task_log
celery -A bot_api_v1.app.tasks.celery_app worker --loglevel=debug -Q celery,bad_news -P solo -n task_bad_news


/Users/v9/Documents/workspace/v9/code/bot-api-v1/venv/bin/python -m uvicorn bot_api_v1.app.core.app_factory:create_app --reload --host 0.0.0.0 --port=8083 --workers=4 --loop=uvloop --http=httptools
/Users/v9/Documents/3---work/06---dev---python/bot-api-v1/bot_api_v1/venv/bin/python -m uvicorn bot_api_v1.app.core.app_factory:create_app --reload --host 0.0.0.0 --port=8083 --workers=4 --loop=uvloop --http=httptools



export PYTHONPATH="/Users/v9/Documents/3---work/06---dev---python/bot-api-v1/bot_api_v1/src:$PYTHONPATH"
venv/bin/python -m uvicorn bot_api_v1.app.core.app_factory:create_app --reload --host 0.0.0.0 --port=8083 --workers=4 --loop=uvloop --http=httptools
venv/bin/python -m uvicorn bot_api_v1.app.core.app_factory:create_app --reload --host 0.0.0.0 --port=8083 --loop=uvloop --http=httptools

# 确保你在项目目录中
cd /code/bot_api
# 设置Python路径
export PYTHONPATH=$PWD/src:$PYTHONPATH






# 在您的项目根目录执行
mkdir -p src/bot_api_v1/libs
git submodule add https://github.com/vimson999/Spider_XHS.git src/bot_api_v1/libs/spider_xhs
git submodule update --init --recursive

cat src/bot_api_v1/libs/spider_xhs/requirements.txt >> requirements.txt
pip install -r requirements.txt

cd src/bot_api_v1/libs/spider_xhs
apt install npm
npm install
npm install jsdom --save

git submodule add https://github.com/vimson999/TikTokDownloader.git src/bot_api_v1/libs/tiktok_downloader
git submodule update --init --recursive

cat src/bot_api_v1/libs/tiktok_downloader/requirements.txt >> requirements.txt
pip install -r requirements.txt

pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

export PYTHONPATH="/Users/v9/Documents/3---work/06---dev---python/bot-api-v1/bot_api_v1/src:$PYTHONPATH"

nvm install --lts
npm --version
nvm alias default 22.14.0


# 确保你在项目目录中
cd /code/bot_api
# 设置Python路径
export PYTHONPATH=$PWD/src:$PYTHONPATH


sudo supervisorctl restart all

sudo supervisorctl restart fastapi_app
sudo supervisorctl restart celery_worker_A
sudo supervisorctl restart celery_worker_log

sudo supervisorctl status

sudo supervisorctl restart celery_whisper_worker
sudo supervisorctl status



cd /Users/v9/Documents/workspace/v9/code/bot-api-v1/src/bot_api_v1/app/static/
/Users/v9/Documents/workspace/v9/code/bot-api-v1/venv/bin/python -m http.server 8080
http://127.0.0.1:8080/src/bot_api_v1/app/static/html/m1.html
http://127.0.0.1:8083/static/html/m1.html



https://www.douyin.com/video/7475254041207950642



export HTTP_PROXY="http://127.0.0.1:7897"
export HTTPS_PROXY="http://127.0.0.1:7897"
export NO_PROXY="localhost,127.0.0.1"

curl -v https://www.google.com


https://ycn0x2weafez.feishu.cn/wiki/L7fowrTE2ilbpDkGVvfcXWWdnRg?table=tblsqLAMgl5DuBCT&view=vewzL2GD3h
https://ycn0x2weafez.feishu.cn/wiki/L7fowrTE2ilbpDkGVvfcXWWdnRg?table=tblsqLAMgl5DuBCT&view=vewzL2GD3h


http://101.35.56.140:3000/login?redirectTo=%2Fexplore%3FschemaVersion%3D1%26panes%3D%257B%2522ya1%2522%253A%257B%2522datasource%2522%253A%2522eejrh83w7sxkwf%2522%252C%2522queries%2522%253A%255B%257B%2522refId%2522%253A%2522A%2522%252C%2522expr%2522%253A%2522%257Binstance%253D%255C%2522fastapi_app%255C%2522%257D%2B%257C%253D%2B%2560%2560%2522%252C%2522queryType%2522%253A%2522range%2522%252C%2522datasource%2522%253A%257B%2522type%2522%253A%2522loki%2522%252C%2522uid%2522%253A%2522eejrh83w7sxkwf%2522%257D%252C%2522editorMode%2522%253A%2522builder%2522%252C%2522direction%2522%253A%2522backward%2522%257D%255D%252C%2522range%2522%253A%257B%2522from%2522%253A%2522now-3h%2522%252C%2522to%2522%253A%2522now%2522%257D%252C%2522panelsState%2522%253A%257B%2522logs%2522%253A%257B%2522visualisationType%2522%253A%2522logs%2522%252C%2522columns%2522%253A%257B%25220%2522%253A%2522Time%2522%252C%25221%2522%253A%2522Line%2522%252C%25222%2522%253A%2522host%2522%252C%25223%2522%253A%2522instance%2522%252C%25224%2522%253A%2522job%2522%257D%252C%2522labelFieldName%2522%253A%2522labels%2522%252C%2522refId%2522%253A%2522A%2522%257D%257D%257D%257D%26orgId%3D1




http://iw6i1vjj93ml.guyubao.com/api/wechat_mp/callback

iw6i1vjj93ml.guyubao.com



'<xml>
  <appid>wxa690d4c27e35c4a2</appid>
  <mch_id>1716724012</mch_id>
  <nonce_str>fc7ae356df8bbb880a5572f8aa0ffaa5</nonce_str>
  <body>88折 | 基础积分包 | 1000 积分 | 限时优惠 | 购买即可获得1000积分</body>
  <out_trade_no>WX17471201751220</out_trade_no>
  <total_fee>1</total_fee>
  <spbill_create_ip>127.0.0.1</spbill_create_ip>
  <notify_url>http://iw6i1vjj93ml.guyubao.com/api/wechat_mp/payment/notify</notify_url>
  <trade_type>JSAPI</trade_type>
  <openid>oFpP87CXMDD5_v0fZUBbchDBNhH8</openid>
  <sign>C98ACBB21A5C5C6F69CF660529C28377</sign>
</xml>'

{'return_code': 'SUCCESS', 
'return_msg': 'OK', 
'result_code': 'SUCCESS', 
'mch_id': '1716724012', 
'appid': 'wxa690d4c27e35c4a2',
 'nonce_str': '5UnbrwT4i4bSuGkU', 
 'sign': 'C18A80FD655C21B0AF1A931D87BD4846', 
 'prepay_id': 'wx13151205631395cd4492461bdfa2870000', '
 trade_type': 'JSAPI'}



 一键提取视频核心信息,只需粘贴视频链接 (支持DY、小X书、快X手、B站等主流平台)，表格自动抓取标题、作者、各项数据指标、封面、视频文案原文！ 获取免费api_key 可以参考：
 短视频的地址链接，格式为string类型

提取短视频文案所需的API密钥，密钥为string类型。

提取抖音小红书B站快手视频信息



https://www.douyin.com/video/7475254041207950642
50871805b4160a5f51b44b235e4f3c8eda33cebcb03f985544db72f3a1dac6ba
94b683b5ce3dcca21393292c165ca964df40541ace868894911b3e9f5fbf7a06
4b51782031927320c80b704ef2c6d1fee7e5d87d468f5b7e7494f3f586c521ac



地址是
6.12 12/09 e@B.gO Ljp:/ 女人过了三十岁必须要拥有的一支口红！而且它只有中国人才能做得出来！  https://v.douyin.com/0CNU3pv1wiQ/ 复制此链接，打开Dou音搜索，直接观看视频！
api_key是
50871805b4160a5f51b44b235e4f3c8eda33cebcb03f985544db72f3a1dac6ba

https://www.xiaohongshu.com/explore/682ae26e000000002300eccd?xsec_token=ABhHe13KV7aZyonWHAeTdIJfKgu8neQ8fcjiHHwvkuFI0=&xsec_source=pc_feed
https://www.xiaohongshu.com/explore/682ae26e000000002300eccd?xsec_token=ABhHe13KV7aZyonWHAeTdIJfKgu8neQ8fcjiHHwvkuFI0=&xsec_source=



当前调试已处理完毕
execute执行结果：
{
  "code": 0,
  "data": {
    "id": "1747721810383",
    "file_link": "标题：小米芯片之路\n作者：雷军\n点赞数：25390  收藏数：1689  评论数：5045  分享数：0\n笔记链接：https://www.xiaohongshu.com/explore/682aa19a000000002202af73?xsec_token=ABhHe13KV7aZyonWHAeTdIJZFF1BNgUiOlouNjh0ihNfM=&xsec_source=\n\n标题：Xiaomi Will Pay You for What??? 📱💼\n作者：AffiliateX ROI\n点赞数：123  收藏数：81  评论数：17  分享数：0\n笔记链接：https://www.xiaohongshu.com/explore/6824bf48000000000f03b754?xsec_token=AB1cHRj5jNKCOGr1v6XNX0DnO8ZOPSJcL0HV_s_ydjae4=&xsec_source=\n\n标题：无标题\n作者：小红薯6821710B\n点赞数：0  收藏数：0  评论数：1  分享数：0\n笔记链接：https://www.xiaohongshu.com/explore/682c16a3000000000303b92f?xsec_token=ABf6Y0JJZqLLlaRtTIGFfTBdPemyouAhcpvr-P5rgOUxM=&xsec_source=\n",
    "total_required": 1,
    "primaryProperty": "使用关键字【小米】-搜索平台【xiaohongshu】-得到【3】条结果,消耗【1】积分"
  }
}

curl -X POST \
  'http://localhost:8083/api/media/kol' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.xiaohongshu.com/user/profile/5b73ad89abe85900018c4d46?xsec_token=ABO2c1MClUMbsXckATU6Cd6ZaEI2fGJ4me_10kENhhKoo=&xsec_source=pc_feed"
  }'


'{"tab_public": {"collection": false, "collectionNote": {"lock": false, "count": 0, "display": false}, "collectionBoard": {"count": 0, "display": false, "lock": false}}, "extra_info": {"fstatus": "none", "blockType": "DEFAULT"}, "result": {"success": true, "code": 0, "message": "success"}, "basic_info": {"imageb": "https://sns-avatar-qc.xhscdn.com/avatar/1040g2jo31g5ummkghs0g4aefj3moija671caumg?imageView2/2/w/540/format/webp", "nickname": "\\u8bf7\\u53eb\\u6211\\u53a8\\u795e", "images": "https://sns-avatar-qc.xhscdn.com/avatar/1040g2jo31g5ummkghs0g4aefj3moija671caumg?imageView2/2/w/360/format/webp", "red_id": "606405531", "gender": 1, "ip_location": "\\u5e7f\\u4e1c", "desc": "\\ud83d\\udc9b\\u62e5\\u6709\\u53a8\\u9f8427\\u5e74\\n\\ud83d\\udc9a\\u4f60\\u53ef\\u4ee5\\u6c38\\u8fdc\\u76f8\\u4fe1\\u6211\\u7684\\u53a8\\u827a\\n\\ud83d\\udcee2\\ufe0f\\u20e35\\ufe0f\\u20e32\\ufe0f\\u20e34\\ufe0f\\u20e39\\ufe0f\\u20e36\\ufe0f\\u20e30\\ufe0f\\u20e38\\ufe0f\\u20e38\\ufe0f\\u20e3\\ud83d\\udc27\\ud83d\\udc27com"}, "interactions": [{"name": "\\u5173\\u6ce8", "count": "16", "type": "follows"}, {"type": "fans", "name": "\\u7c89\\u4e1d", "count": "996"}, {"count": "18250", "type": "interaction", "name": "\\u83b7\\u8d5e\\u4e0e\\u6536\\u85cf"}], "tags": [{"icon": "http://ci.xiaohongshu.com/icons/user/gender-female-v1.png", "tagType": "info"}, {"name": "\\u5e7f\\u4e1c\\u6df1\\u5733", "tagType": "location"}]}'
[{'type': 'video', 'display_title': '🍜超适合懒人的葱油拌面', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '680518d2000000001b024fc9', 'xsec_token': 'ABVX6fVwbWUeYFpCYlfOavDq3erBDgpmSMIyL43rkAX9E='}, {'cover': {...}, 'note_id': '68123a48000000002001f831', 'xsec_token': 'ABN8zcwzllh2KbnU_rt158yg3sg55qY68cQFUEWmfNwh8=', 'type': 'video', 'display_title': '🍜这个拌面在网上那么火不是没有原因的', 'user': {...}, 'interact_info': {...}}, {'type': 'video', 'display_title': '🍜 如果我开店，这一定是招牌面❗❗❗', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '682b5b1b000000002102e4ad', 'xsec_token': 'ABhMMqYpIC0vB5D7YQ2IfC4h0LXZM13RBmorkJdJJSjUM='}, {'type': 'video', 'display_title': '🍜真的巨巨巨…巨好吃🔥', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '6828b26c0000000021008a33', 'xsec_token': 'ABMkv-qk791RJA-rhPFh9V0piz6nkYloeAmVWfSBTzmcg='}, {'note_id': '6828a30f000000002100f01c', 'xsec_token': 'ABMkv-qk791RJA-rhPFh9V0nNjdlPGwof6tH_CbTMFw0Y=', 'type': 'video', 'display_title': '🍜大家都喜欢吃的红油煎蛋泡面🔥🔥🔥', 'user': {...}, 'interact_info': {...}, 'cover': {...}}, {'type': 'video', 'display_title': '🍜这个拌面配方可以去开店了❗ ❗ ❗', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '68275ab5000000002001da0c', 'xsec_token': 'AB-oIh2wtPxzjVh5o-xmgnbOn5PNUViFR8fmRczeJ37A0='}, {'note_id': '6824c357000000002100cb79', 'xsec_token': 'ABB4NCWq2o3RlurcISFEys7Eea-wAOTYP40EJfHsgxw0I=', 'type': 'video', 'display_title': '🍜这个拌面配方可以去开店了', 'user': {...}, 'interact_info': {...}, 'cover': {...}}, {'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '682367f9000000002001c6d8', 'xsec_token': 'ABXwmwUfp7IHXw2yTuLHACwQpvRJFXRFCYp9N4aNaUpWQ=', 'type': 'video', 'display_title': '答应我❗一定要试试这个面条'}, {'interact_info': {...}, 'cover': {...}, 'note_id': '6821ffb2000000002001ecc6', 'xsec_token': 'ABJmZVvTP7Csawc4mn1asR6BuzBhW8Yxx-R7c0Bl7ZK4U=', 'type': 'video', 'display_title': '🍜这个拌面配方可以去开店了', 'user': {...}}, {'type': 'video', 'display_title': '🍜如果我开店，这一定是招牌面', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '6820b850000000002001eb8c', 'xsec_token': 'ABFAle5fndi54rjMeZvhWsYw1NxnPpdH9B_EFonCme9TQ='}, {'display_title': '🍜如果我开店，这一定是招牌面', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '681a2b900000000022026e91', 'xsec_token': 'ABqAU2enuDhcB1GEzkmoKGLPmndkZfdgSIdF3G9A1LnJM=', 'type': 'video'}, {'interact_info': {...}, 'cover': {...}, 'note_id': '681631f300000000220250a8', 'xsec_token': 'ABZr98qc0R2usnMtcRqw1Ir2dGK0FrHLe0mVXxAczf-Io=', 'type': 'video', 'display_title': '🍜这个拌面配方可以去开店了', 'user': {...}}, {'note_id': '680f97e9000000002100db1d', 'xsec_token': 'ABBUopo2vKqu9oSGlsRCJ0bjj9VbuGMVp4q84yTkWGAuI=', 'type': 'video', 'display_title': '🍜这滋味只有吃过的人懂', 'user': {...}, 'interact_info': {...}, 'cover': {...}}, {'xsec_token': 'ABp66kCrf1ByWU8DyB79GRsOFQ7pSVQoqk3NYSEafHL2s=', 'type': 'video', 'display_title': '🍜红油煮个金拉面吃吃', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '680cfb8d000000001e007df0'}, {'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67ffd3fc000000001b03e1f8', 'xsec_token': 'AB366ISGbyqYQ_lUWiJgGK9ySxRKZxczbbI34AV_meKNo=', 'type': 'video', 'display_title': '🍜妈妈教的葱油拌面升级了'}, {'type': 'video', 'display_title': '煮个番茄鸡蛋面吃吃 ', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67f67f5b000000001b025db6', 'xsec_token': 'AB6xb-C5_R7-32x_PEhQrCm3Wos2uxD5541dN7BA0QfMQ='}, {'type': 'video', 'display_title': '清空冰箱煮一碗好吃的辛拉面', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67efe892000000001d024b03', 'xsec_token': 'AB6JueoXtVW-1p6ZlWdG9ok6dwWF6lkgjWouoV8yP4Gps='}, {'interact_info': {...}, 'cover': {...}, 'note_id': '67e91f45000000001d004966', 'xsec_token': 'ABBtn8ylwmSVmUOH1oD5GajGPL4BTGaiF61b2ot0Iumyk=', 'type': 'video', 'display_title': '跟着潘玮柏煮泡面🍜', 'user': {...}}, {'note_id': '67e524ab000000001d02c0e0', 'xsec_token': 'ABxyvjM1iTgdzTusd--qTxcfp5_RUWxyeoBqyORNHgIJ4=', 'type': 'video', 'display_title': '打工人如何快速吃上饭', 'user': {...}, 'interact_info': {...}, 'cover': {...}}, {'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67d2f009000000001d01d540', 'xsec_token': 'ABtPQhAk_9zWsQ_OTsecVhCjZmfSNF6D9W0g7DPmlMZE4=', 'type': 'video', 'display_title': '我妈这个葱油拌面真的很绝❗️'}, {'type': 'video', 'display_title': '试试这个泡面做法❗️❗️❗️', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67cb108f000000002903b428', 'xsec_token': 'ABUlvxCApwaW9j6ghf2p1HQLjMfUgXFJ4kT3Zavq-QN-w='}, {'display_title': '搞点红油煎鸡蛋香肠鱼丸泡面吃吃❗️❗️', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67c5a22e00000000290139bd', 'xsec_token': 'AB154l2iHqMe-AYw1I_w0eFfIz17YIqgfaiRapcOH8lBs=', 'type': 'video'}, {'type': 'video', 'display_title': '请所有人谨记这个做法🔥', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67b33ee00000000029035661', 'xsec_token': 'ABFzYI-BBphFCuAk7ty8il8wmpmT2N2FiHd8zY1HmSpqA='}, {'type': 'video', 'display_title': '谁能拒绝芝士面啊❗❗❗', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67af4978000000002903ab9d', 'xsec_token': 'ABKCZ2Nv2kMDB3N8sEVX4o_s0uKEf2q82tYn3pv696q3s='}, {'display_title': '🔥10万人看过我煮泡面，煮个辛拉面感谢大家', 'user': {...}, 'interact_info': {...}, 'cover': {...}, 'note_id': '67aa168f000000002503c998', 'xsec_token': 'ABhf7-6-c6Z6867dZy6sBROn_teddHfszY74_RLwzaNiQ=', 'type': 'video'}, {'cover': {...}, 'note_id': '67a6043a000000002602de6e', 'xsec_token': 'ABIm_-1S_5jit6dnlAquMjbmjx2Is2sFF-lZcIu0AXLgo=', 'type': 'video', 'display_title': '🔥泡面的神仙吃法｜黏糊糊芝士年糕火鸡面', 'user': {...}, 'interact_info': {...}}, {'note_id': '679f78f8000000002803e503', 'xsec_token': 'AB71EcYyh1EAlgUOS-_S3mExS1-oERVEpktCbhHqtS9iU=', 'type': 'video', 'display_title': '我宣布❗️这是泡面最好吃的做法', 'user': {...}, 'interact_info': {...}, 'cover': {...}}, {'interact_info': {...}, 'cover': {...}, 'note_id': '6797926d000000002a000fa0', 'xsec_token': 'ABXpwLUjnYmSchHEx0WR9sWFtTKKDYoKiyBEbdKtM_mME=', 'type': 'video', 'display_title': '搞点红油煎蛋香肠泡面吃吃', 'user': {...}}, {'interact_info': {...}, 'cover': {...}, 'note_id': '67922271000000002901fdaa', 'xsec_token': 'ABIwOSbDtoOO_rFY0jDCjY82GXczmf_yC9OCpjLUFETkc=', 'type': 'video', 'display_title': '所有人谨记这个吃法❗❗❗', 'user': {...}}]





我希望返回的结构是
{
  名字,
  性别,
  签名,
  粉丝数,
  关注数,
  获赞数,
  发布视频数,
  较昨天新增粉丝,
  较昨天新增获赞,
  较昨天新增发布数,
  词云标签,
  发布的视频:[
    {
      标题,
      点赞数,
      评论数,
      分享数,
      观看数,
      发布时间,
      视频链接
    }
  ]
}




是否植入广告
广告的品牌
关联热门、热点话题、挑战
评论的词云
高互动的粉丝画像
点赞、收藏、分享、播放数均值比较



视频----
内含广告信息
与今日关联热门、热点话题、挑战
评论详情列表
评论的词云
高赞评论
较同作者其他视频相比值 点赞/收藏/分享/评论数
同视频较昨日新增播放/点赞/收藏/分享/评论数
同视频7日新增播放/点赞/收藏/分享/评论数



KOL
变现模式 
均值 
远超均值视频数量 
头牌 
商单品牌 
橱窗商品 
橱窗爆品 
带货类型 
直播场次 
最近直播时间




curl -X POST \
  'http://localhost:8083/api/tt/upro' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.douyin.com/user/MS4wLjABAAAAyeRQDmzlFJJ-WJ3mfkvN2IfTei6Mm7nTwkX5wz5hfxk"
  }'


curl -X POST \
  'http://localhost:8083/api/tt/vcl' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://v.douyin.com/YX-HGKSVNzU"
  }'


curl -X POST \
  'http://localhost:8083/api/tt/vcl' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.douyin.com/video/7490501357934333196"
  }'

curl -X POST \
  'http://localhost:8083/api/tt/vcl' \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.xiaohongshu.com/explore/67e2b3f900000000030286ce?xsec_token=ABsttmnMANeopanZhB7mwrTWl3izLUb0_nFBSUxqS4EZk=&xsec_source=pc_feed"
  }'





-- 1. 视频元数据表
CREATE TABLE IF NOT EXISTS meta_video_info (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform VARCHAR(50) NOT NULL,
    platform_video_id VARCHAR(255) NOT NULL,
    original_url TEXT NOT NULL,
    title TEXT,
    description TEXT,
    content_text TEXT,
    tags TEXT[], -- 标签数组
    initial_play_count BIGINT DEFAULT 0,
    initial_like_count BIGINT DEFAULT 0,
    initial_comment_count BIGINT DEFAULT 0,
    initial_share_count BIGINT DEFAULT 0,
    initial_collect_count BIGINT DEFAULT 0,
    cover_url TEXT,
    video_url TEXT,
    duration_seconds INTEGER,
    published_at TIMESTAMP WITH TIME ZONE,
    uploader_user_id UUID REFERENCES meta_user(id) ON DELETE SET NULL, -- 关联到 meta_user 表
    data_last_fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status SMALLINT DEFAULT 1 NOT NULL CHECK (status IN (0, 1, 2)),
    memo TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- CREATE UNIQUE INDEX IF NOT EXISTS idx_meta_video_info_platform_platform_video_id ON meta_video_info (platform, platform_video_id);
-- CREATE INDEX IF NOT EXISTS idx_meta_video_info_uploader_user_id ON meta_video_info (uploader_user_id);
-- CREATE INDEX IF NOT EXISTS idx_meta_video_info_published_at ON meta_video_info (published_at DESC);
-- CREATE INDEX IF NOT EXISTS idx_meta_video_info_tags ON meta_video_info USING GIN (tags); -- GIN索引用于数组搜索

COMMENT ON TABLE meta_video_info IS '存储视频的核心元数据';
COMMENT ON COLUMN meta_video_info.platform_video_id IS '视频在源平台的唯一ID';
COMMENT ON COLUMN meta_video_info.tags IS '视频标签，包括普通标签和Hashtags';
COMMENT ON COLUMN meta_video_info.uploader_user_id IS '上传者/KOL在meta_user表中的ID';
COMMENT ON COLUMN meta_video_info.data_last_fetched_at IS '本条记录数据最后从源平台拉取的时间';


-- 2. 视频日统计表
CREATE TABLE IF NOT EXISTS statistics_video_daily (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_info_id UUID NOT NULL REFERENCES meta_video_info(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    play_count BIGINT DEFAULT 0,
    like_count BIGINT DEFAULT 0,
    comment_count BIGINT DEFAULT 0,
    share_count BIGINT DEFAULT 0,
    collect_count BIGINT DEFAULT 0,
    status SMALLINT DEFAULT 1 NOT NULL CHECK (status IN (0, 1, 2)),
    memo TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- CREATE UNIQUE INDEX IF NOT EXISTS idx_statistics_video_daily_video_snapshot ON statistics_video_daily (video_info_id, snapshot_date);
-- CREATE INDEX IF NOT EXISTS idx_statistics_video_daily_snapshot_date ON statistics_video_daily (snapshot_date DESC);

COMMENT ON TABLE statistics_video_daily IS '存储视频每日的动态统计数据快照';
COMMENT ON COLUMN statistics_video_daily.video_info_id IS '关联的meta_video_info表中的视频ID';
COMMENT ON COLUMN statistics_video_daily.snapshot_date IS '统计数据快照的日期';


-- 3. KOL日统计表
CREATE TABLE IF NOT EXISTS statistics_kol_daily (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES meta_user(id) ON DELETE CASCADE, -- 关联到 meta_user 表
    snapshot_date DATE NOT NULL,
    follower_count BIGINT DEFAULT 0,
    following_count BIGINT DEFAULT 0,
    total_videos_count INTEGER DEFAULT 0,
    total_likes_received_on_videos BIGINT DEFAULT 0,
    total_comments_received_on_videos BIGINT DEFAULT 0,
    total_shares_on_videos BIGINT DEFAULT 0,
    total_collections_on_videos BIGINT DEFAULT 0,
    total_plays_on_videos BIGINT DEFAULT 0,
    status SMALLINT DEFAULT 1 NOT NULL CHECK (status IN (0, 1, 2)),
    memo TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- CREATE UNIQUE INDEX IF NOT EXISTS idx_statistics_kol_daily_user_snapshot ON statistics_kol_daily (user_id, snapshot_date);
-- CREATE INDEX IF NOT EXISTS idx_statistics_kol_daily_snapshot_date ON statistics_kol_daily (snapshot_date DESC);

COMMENT ON TABLE statistics_kol_daily IS '存储KOL每日的动态统计数据快照';
COMMENT ON COLUMN statistics_kol_daily.user_id IS '关联的meta_user表中的用户ID (KOL)';
COMMENT ON COLUMN statistics_kol_daily.follower_count IS 'KOL的粉丝数';
COMMENT ON COLUMN statistics_kol_daily.total_videos_count IS 'KOL发布的作品总数';
COMMENT ON COLUMN statistics_kol_daily.total_likes_received_on_videos IS 'KOL所有作品累计获得的赞数';

-- -- 触发器函数，用于自动更新 updated_at 字段
-- CREATE OR REPLACE FUNCTION trigger_set_timestamp()
-- RETURNS TRIGGER AS $$
-- BEGIN
--   NEW.updated_at = NOW();
--   RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;

-- -- 为每个表创建触发器
-- CREATE TRIGGER set_timestamp_meta_video_info
-- BEFORE UPDATE ON meta_video_info
-- FOR EACH ROW
-- EXECUTE FUNCTION trigger_set_timestamp();

-- CREATE TRIGGER set_timestamp_statistics_video_daily
-- BEFORE UPDATE ON statistics_video_daily
-- FOR EACH ROW
-- EXECUTE FUNCTION trigger_set_timestamp();

-- CREATE TRIGGER set_timestamp_statistics_kol_daily
-- BEFORE UPDATE ON statistics_kol_daily
-- FOR EACH ROW
-- EXECUTE FUNCTION trigger_set_timestamp();


CREATE TABLE IF NOT EXISTS meta_kol_info (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform VARCHAR(50) NOT NULL,
    platform_kol_id VARCHAR(255) NOT NULL,
    profile_url TEXT,
    nickname VARCHAR(255),
    bio TEXT,
    avatar_url TEXT,
    cover_url TEXT,
    gender SMALLINT CHECK (gender IN (0, 1, 2)), -- 0:未知, 1:男, 2:女
    region VARCHAR(100),
    city VARCHAR(100),
    country VARCHAR(100),
    verified BOOLEAN DEFAULT FALSE,
    verified_reason TEXT,
    initial_follower_count BIGINT DEFAULT 0,
    initial_following_count BIGINT DEFAULT 0,
    initial_video_count INTEGER DEFAULT 0,
    data_last_fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status SMALLINT DEFAULT 1 NOT NULL CHECK (status IN (0, 1, 2)), -- 0:失效, 1:正常, 2:待审核
    memo TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- CREATE UNIQUE INDEX IF NOT EXISTS idx_meta_kol_info_platform_platform_kol_id ON meta_kol_info (platform, platform_kol_id);
-- CREATE INDEX IF NOT EXISTS idx_meta_kol_info_nickname ON meta_kol_info (nickname); -- 如果常按昵称搜索

COMMENT ON TABLE meta_kol_info IS '存储KOL/博主的元数据信息';
COMMENT ON COLUMN meta_kol_info.platform_kol_id IS 'KOL在源平台的唯一ID';
COMMENT ON COLUMN meta_kol_info.data_last_fetched_at IS '本条记录数据最后从源平台拉取的时间';



# 启动 Celery Worker (确保它能加载到您的任务定义)
celery -A bot_api_v1.app.tasks.celery_app worker -l info -Q celery,media_extraction,logging,your_scheduled_task_queue # 可以为定时任务指定单独队列

# 启动 Celery Beat (在另一个终端或后台)
celery -A bot_api_v1.app.tasks.celery_app beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler # 如果使用数据库存储调度状态，否则默认即可