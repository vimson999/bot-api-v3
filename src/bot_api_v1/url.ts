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
      id: 'test-auth-key-123456',// 授权的id，用于context.fetch第三个参数以区分该请求使用哪个授权
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
      }, 'test-auth-key-123456');
      
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



// {
//     "authorizations": [
//         [
//             "test-auth-key-123456"
//         ]
//     ]
// }


