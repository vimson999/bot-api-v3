import os
import sys
from pathlib import Path


# 设置项目根目录路径
ROOT_DIR = Path(__file__).parent.parent.parent
# 设置 NODE_PATH 指向子模块的 node_modules 目录
os.environ["NODE_PATH"] = str(ROOT_DIR / "bot_api_v1" / "libs" / "spider_xhs" / "node_modules")
print(f"NODE_PATH 环境变量已设置为: {os.environ['NODE_PATH']}")

# 添加源码路径
sys.path.insert(0, str(ROOT_DIR))

from bot_api_v1.app.services.business.temp_xhs_service import XHSService

# 从根目录的cookies.txt获取Cookie
# cookie_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cookies_xhs.txt")
cookie_file = '/Users/v9/Documents/workspace/v9/code/bot-api-v1/src/bot_api_v1/app/config/cookies/cookies_xhs.txt'

def test_get_note_info():
    service = XHSService(cookie_file)
    # 使用一个有效的笔记URL进行测试
    note_url = "https://www.xiaohongshu.com/explore/64674a91000000001301762e?xsec_token=ABAJcy_294mBZauFhAac6izmJvYB6yqm49MAtXSVU8XA4=&xsec_source=pc_feed"
    success, msg, note_info = service.get_note_info(note_url)
    
    assert success, f"获取笔记失败: {msg}"
    assert note_info is not None
    assert "title" in note_info
    assert "desc" in note_info
    assert "note_type" in note_info
    
    print(f"标题: {note_info['title']}")
    print(f"描述: {note_info['desc'][:50]}...")
    print(f"类型: {note_info['note_type']}")

    print(f"note_info is  {note_info}")


def test_search_notes():
    service = XHSService(cookie_file)
    keyword = "旅行"
    success, msg, notes = service.search_notes(keyword, limit=5)
    
    assert success, f"搜索笔记失败: {msg}"
    assert notes is not None
    assert len(notes) > 0
    
    print(f"共搜索到 {len(notes)} 条结果")
    for i, note in enumerate(notes[:3]):
        print(f"{i+1}. {note.get('title', '无标题')}")
        


# 在测试函数开始之前添加
def verify_node_modules():
    import os
    node_path = os.environ.get("NODE_PATH", "未设置")
    print(f"NODE_PATH: {node_path}")
    
    # 检查目录是否存在
    if node_path != "未设置":
        jsdom_path = os.path.join(node_path, "jsdom")
        if os.path.exists(jsdom_path):
            print(f"jsdom 模块目录存在: {jsdom_path}")
        else:
            print(f"ERROR: jsdom 模块目录不存在: {jsdom_path}")
    
    # 尝试使用 Node.js 检查模块是否可用
    import subprocess
    try:
        result = subprocess.run(
            ["node", "-e", "try { require('jsdom'); console.log('jsdom module found'); } catch(e) { console.error(e.message); }"],
            capture_output=True, text=True, check=False
        )
        print(f"Node.js 检查结果: {result.stdout or result.stderr}")
    except Exception as e:
        print(f"执行 Node.js 检查时出错: {e}")


# 在第三个文件中添加更多测试方法：

def test_get_user_info():
    service = XHSService(cookie_file)
    # 使用一个有效的用户URL进行测试
    user_url = "https://www.xiaohongshu.com/user/profile/5a6b47644eacab3de7975ddf?channel_type=web_note_detail_r10&xsec_token=ABijFpZkH5mZK4h-LIfDSQol45d67-X2W_5xUDLjwoL50%3D&xsec_source=pc_note"
    success, msg, user_info = service.get_user_info(user_url)
    
    assert success, f"获取用户信息失败: {msg}"
    assert user_info is not None
    # assert "nickname" in user_info
    # assert "follower_count" in user_info
    
    # print(f"用户昵称: {user_info['nickname']}")
    # print(f"粉丝数: {user_info['follower_count']}")
    print(f"user_info is  {user_info}")

def test_get_note_comments():
    service = XHSService(cookie_file)
    # 使用一个有效的笔记URL进行测试
    note_url = "https://www.xiaohongshu.com/explore/64674a91000000001301762e?xsec_token=ABAJcy_294mBZauFhAac6izmJvYB6yqm49MAtXSVU8XA4=&xsec_source=pc_feed"
    success, msg, comments = service.get_note_comments(note_url)
    
    assert success, f"获取笔记评论失败: {msg}"
    assert comments is not None
    assert len(comments) > 0
    
    print(f"共获取到 {len(comments)} 条评论")
    for i, comment in enumerate(comments[:3]):
        print(f"{i+1}. {comment.get('content', '无内容')}")

def test_get_search_keywords():
    service = XHSService(cookie_file)
    keyword = "旅行"
    success, msg, keywords = service.get_search_keywords(keyword)
    
    assert success, f"获取搜索关键词失败: {msg}"
    assert keywords is not None
    assert len(keywords) > 0
    
    print(f"共获取到 {len(keywords)} 条关键词推荐")
    for i, kw in enumerate(keywords[:5]):
        print(f"{i+1}. {kw}")

def test_download_note_media():
    service = XHSService(cookie_file)
    # 使用一个有效的笔记URL进行测试
    note_url = "https://www.xiaohongshu.com/explore/64674a91000000001301762e?xsec_token=ABAJcy_294mBZauFhAac6izmJvYB6yqm49MAtXSVU8XA4=&xsec_source=pc_feed"
    
    # 创建一个临时下载目录
    import tempfile
    temp_dir = tempfile.mkdtemp()
    
    success, msg, save_path = service.download_note_media(note_url, save_path=temp_dir)
    
    assert success, f"下载笔记媒体失败: {msg}"
    assert save_path is not None
    
    import os
    assert os.path.exists(save_path), f"下载路径不存在: {save_path}"
    
    print(f"媒体文件下载成功，保存路径: {save_path}")


# 在 __main__ 中添加这些测试
if __name__ == "__main__":
    verify_node_modules()

    print("测试获取笔记信息...")
    test_get_note_info()
    
    # print("\n测试搜索笔记...")
    # test_search_notes()
    
    print("\n测试获取用户信息...")
    test_get_user_info()
    
    # print("\n测试获取笔记评论...")
    # test_get_note_comments()
    
    # print("\n测试获取搜索关键词...")
    # test_get_search_keywords()
    
    # print("\n测试下载笔记媒体...")
    # test_download_note_media()

# 在测试前调用此函数
# verify_node_modules()






