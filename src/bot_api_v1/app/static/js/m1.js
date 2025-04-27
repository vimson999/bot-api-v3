// --- 前端 JavaScript ---

// 假设 CryptoJS 库已加载

document.getElementById('fetch-btn').addEventListener('click', fetchVideoInfo);
document.getElementById('video-url').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') fetchVideoInfo();
});

// --- Helper Function: Convert Uint8Array to CryptoJS WordArray ---
function uint8ArrayToWordArray(uint8Array) {
    const words = [];
    for (let i = 0; i < uint8Array.length; i++) {
        words[i >>> 2] |= uint8Array[i] << (24 - (i % 4) * 8);
    }
    return CryptoJS.lib.WordArray.create(words, uint8Array.length);
}

// --- Helper Function: Convert CryptoJS WordArray to Base64 ---
function wordArrayToBase64(wordArray) {
    return CryptoJS.enc.Base64.stringify(wordArray);
}

// --- Helper Function: Convert Base64 to CryptoJS WordArray ---
// (Potentially needed if you were decrypting on the frontend)
// function base64ToWordArray(base64Str) {
//    return CryptoJS.enc.Base64.parse(base64Str);
// }

async function fetchVideoInfo() {
    const url = document.getElementById('video-url').value.trim();
    const detailSection = document.getElementById('video-detail-section');
    const detailContent = document.getElementById('video-detail-content');
    // !! 重要: 获取你的静态 API Token 的方式取决于你的应用 !!

    if (!url) {
        detailSection.style.display = 'none';
        return;
    }
    detailSection.style.display = 'none'; // 隐藏旧内容
    detailContent.innerHTML = '正在获取信息，请稍候...';
    detailSection.style.display = 'block'; // 显示加载信息

    try {
        // 1. 获取 ticket
        const ticketRes = await fetch('/api/tkt/get_ticket').then(r => {
            if (!r.ok) throw new Error(`获取 Ticket 失败: ${r.status} ${r.statusText}`);
            return r.json();
        });
        if (!ticketRes.ticket) {
            throw new Error('获取到的 Ticket 为空');
        }
        const ticket = ticketRes.ticket;

        // 2. 用 ticket 作为基础，派生 AES 密钥并加密参数
        const data = JSON.stringify({
            url: url,
            extract_text: false, // 保持和后端接口一致
            include_comments: false // 保持和后端接口一致
        });

        // **修复**: 使用 window.crypto.getRandomValues 生成安全的 IV
        const ivBytes = new Uint8Array(16); // 16 bytes for AES block size
        window.crypto.getRandomValues(ivBytes);
        const ivWordArray = uint8ArrayToWordArray(ivBytes); // 转换为 CryptoJS WordArray

        // **改进**: 使用 SHA-256 哈希 Ticket 生成 256位 (32字节) 的 AES 密钥
        const keyWordArray = CryptoJS.SHA256(ticket); // 直接使用 SHA256 的 WordArray 输出作为 Key

        // 加密 (AES-256-CBC)
        const encrypted = CryptoJS.AES.encrypt(data, keyWordArray, {
            iv: ivWordArray,
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7
        });

        // base64编码密文和IV
        const encryptedBase64 = wordArrayToBase64(encrypted.ciphertext);
        const ivBase64 = wordArrayToBase64(ivWordArray);

        // 3. 调用后端接口，body 传加密数据和iv, headers 传 ticket 和 api_token
        const resp = await fetch('/api/media/e1/bsc', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Ticket': ticket // JWT Ticket for validation and decryption key source
            },
            body: JSON.stringify({ data: encryptedBase64, iv: ivBase64 })
        });

        if (!resp.ok) {
             // 尝试解析错误信息
             let errorDetail = `HTTP 错误: ${resp.status} ${resp.statusText}`;
             try {
                 const errorJson = await resp.json();
                 errorDetail = errorJson.detail || errorDetail; // 使用后端提供的 detail
             } catch (e) { /* 忽略 json 解析错误 */ }
             throw new Error(`请求失败: ${errorDetail}`);
        }

        const res = await resp.json();

        if (res.code !== 200 || !res.data) {
            throw new Error(`获取失败: ${escapeHTML(res.message || '后端返回错误或无数据')}`);
        }

        // 4. 显示结果 (维持原样，但注意 escapeHTML 的重要性)
        const dataObj = res.data;
        /*
         * 注意: 下方的 innerHTML 使用虽然方便，但在复杂应用中
         * 推荐使用更安全的 DOM 操作方法 (createElement, textContent)
         * 或 UI 框架来避免潜在问题并提高可维护性。
         * 当前的 escapeHTML 已处理了 XSS 风险。
         */
        detailContent.innerHTML = `
            <div class="detail-left">
                <img src="${escapeHTML(dataObj.media.cover_url)}" alt="视频封面" class="detail-cover">
            </div>
            <div class="detail-right">
                <div class="detail-block">
                    <div class="detail-row"><span class="detail-label">标题</span><span class="detail-value">${escapeHTML(dataObj.title)}</span></div>
                    <div class="detail-row"><span class="detail-label">标签</span>
                        <span class="detail-value">
                            ${(dataObj.tags||[]).map(tag => `<span class="tag">${escapeHTML(tag)}</span>`).join(" ")}
                        </span>
                    </div>
                </div>
                <div class="detail-block">
                    <div class="detail-row"><span class="detail-label">描述</span>
                        <span class="detail-value" style="white-space:pre-line;">${escapeHTML(dataObj.description)}</span>
                    </div>
                </div>
                <div class="detail-block">
                    <div class="detail-row"><span class="detail-label">统计</span>
                        <span class="detail-value">
                            <span>👍 ${dataObj.statistics.like_count}</span>
                            <span style="margin-left:12px;">💬 ${dataObj.statistics.comment_count}</span>
                            <span style="margin-left:12px;">🔁 ${dataObj.statistics.share_count}</span>
                            <span style="margin-left:12px;">⭐ ${dataObj.statistics.collect_count}</span>
                            <span style="margin-left:12px;">▶️ ${dataObj.statistics.play_count}</span>
                        </span>
                    </div>
                </div>
                <div class="detail-block">
                    <div class="detail-row"><span class="detail-label">作者</span>
                        <span class="detail-value">
                            昵称：${escapeHTML(dataObj.author.nickname)}<br>
                            签名：${escapeHTML(dataObj.author.signature)}<br>
                            粉丝：${dataObj.author.follower_count}，关注：${dataObj.author.following_count}<br>
                            地区：${escapeHTML(dataObj.author.region)}
                        </span>
                    </div>
                </div>
                <div class="detail-block">
                    <div class="detail-row"><span class="detail-label">发布时间</span>
                        <span class="detail-value">${escapeHTML(dataObj.publish_time)}</span>
                    </div>
                </div>
                <div class="detail-block">
                    <div class="detail-row"><span class="detail-label">媒体</span>
                        <span class="detail-value">
                            <a href="m3.html?video_url=${encodeURIComponent(dataObj.media.video_url)}" target="_blank">下载视频</a>
                        </span>
                    </div>
                </div>
            </div>
        `;
        detailSection.style.display = 'block'; // 确保结果区域可见

    } catch (error) {
        console.error("处理视频信息时出错:", error);
        detailContent.innerHTML = `<span style="color:red;">处理失败: ${escapeHTML(error.message)}</span>`;
        detailSection.style.display = 'block'; // 确保错误信息可见
    }
}

// HTML 转义函数 (保持不变)
function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, function(m) {
        return ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[m];
    });
}