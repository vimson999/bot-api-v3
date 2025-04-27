// 获取URL参数
function getQueryParam(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

document.addEventListener('DOMContentLoaded', () => {
    const videoUrl = getQueryParam('video_url');
    const video = document.getElementById('video-player');
    if (videoUrl) {
        // 通过后端代理解决CORS
        video.src = "/api/media/proxy/vd?url=" + encodeURIComponent(videoUrl);
    } else {
        video.outerHTML = '<div style="color:red;">未检测到视频地址</div>';
    }
});