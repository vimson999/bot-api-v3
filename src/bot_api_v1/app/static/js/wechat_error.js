// 获取URL参数
function getQueryParam(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

// 设置错误信息
document.addEventListener('DOMContentLoaded', () => {
    const code = getQueryParam('code') || '';
    const message = getQueryParam('message') || '未知错误';
    
    let title = '错误';
    if (code === '401') title = '授权失败';
    else if (code === '403') title = '访问受限';
    else if (code === '404') title = '资源不存在';
    else if (code === '500') title = '服务异常';
    
    document.getElementById('errorTitle').textContent = title;
    document.getElementById('errorMessage').textContent = decodeURIComponent(message);
});