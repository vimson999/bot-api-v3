from bot_api_v1.app.services.business.xhs_service import XHSService
from bot_api_v1.app.core.logger import logger
import json

service = XHSService()
def test_get_search_keyword():
    return service.get_search_keyword("智能体")

def test_get_note_all_comment():
    return service.get_note_all_comment("")

def test_get_search_some_note():
    return service.get_search_some_note("智能体")
    

# 在 __main__ 中添加这些测试
if __name__ == "__main__":
    # success, msg, res_json = test_get_search_keyword()
    # logger.info(f'获取笔记信息结果 {json.dumps(res_json, ensure_ascii=False)}: {success}, msg: {msg}')

    # success, msg, note_all_comment = test_get_note_all_comment()
    # logger.info(f'获取笔记评论信息结果 {json.dumps(note_all_comment, ensure_ascii=False)}: {success}, msg: {msg}')
    
    success, msg, note_list = test_get_search_some_note()
    logger.info(f'获取笔记列表信息结果 {json.dumps(note_list, ensure_ascii=False)}: {success}, msg: {msg}')

    pass


