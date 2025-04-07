// 获取URL参数
function getQueryParam(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

// 获取用户信息和商品列表
const openid = getQueryParam('openid');
const token = getQueryParam('token');

// 设置返回按钮事件
document.addEventListener('DOMContentLoaded', () => {
    const backButton = document.querySelector('.back-icon');
    if (backButton) {
        backButton.addEventListener('click', () => {
            window.history.back();
        });
    }
});

// 加载商品数据// 加载商品数据
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // 获取商品列表
        const response = await fetch(`/api/wechat_mp/products?token=${token}`);
        if (!response.ok) throw new Error('获取商品失败');
        
        const data = await response.json();
        
        // 渲染商品列表
        const productList = document.getElementById('productList');
        if (data.products && data.products.length > 0) {
            let html = '';
            data.products.forEach(product => {
                // 提取产品特性
                // const tags = Array.isArray(product.tags) ? product.tags : [];
                // const featuresHtml = tags.map(tag => `<span class="feature-tag">${tag}</span>`).join(' ');
                
                const featuresHtml = `<span class="feature-tag">${product.name || '未命名商品'}</span>`

                html += `
                <div class="product-card">
                    <div class="product-image">
                        <img src="/static/img/${product.cover_image || ''}" alt="${product.name || '商品'}">
                    </div>
                    <div class="product-content">
                        <h3 class="product-name">${product.description || '未命名商品'}</h3>
                        <div class="product-features">${featuresHtml}</div>
                        <div class="product-price-row">
                            <div class="product-price">
                                <span class="price-symbol">¥</span>
                                <span class="sale-price">${product.sale_price || 0}</span>
                                <span class="original-price">¥${product.original_price || 0}</span>
                            </div>
                            <button class="buy-btn" data-id="${product.id}" onclick="buyProduct('${product.id}')">立即购买</button>
                        </div>
                    </div>
                </div>
                `;
            });
            productList.innerHTML = html;
        } else {
            productList.innerHTML = '<div class="empty-tip">暂无商品，敬请期待</div>';
        }
    } catch (error) {
        console.error('加载失败:', error);
        productList.innerHTML = '<div class="empty-tip">加载失败，请刷新重试</div>';
    }
});


// ... 现有代码 ...

// 购买商品函数
function buyProduct(productId) {
    // 显示加载中提示
    const loadingToast = document.createElement('div');
    loadingToast.className = 'loading-toast';
    loadingToast.innerHTML = '<div class="spinner"></div><div>正在创建订单...</div>';
    document.body.appendChild(loadingToast);
    
    // 调用后端API创建订单
    fetch('/api/wechat_mp/create_order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            product_id: productId,
            token: token,
            openid: openid
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('创建订单失败');
        }
        return response.json();
    })
    .then(data => {
        // 移除加载提示
        document.body.removeChild(loadingToast);
        
        if (data.code === 0) {
            // 订单创建成功，跳转到支付页面
            window.location.href = `/api/wechat_mp/pay?order_id=${data.data.order_id}&token=${token}`;
        } else {
            // 显示错误信息
            alert(data.message || '创建订单失败，请重试');
        }
    })
    .catch(error => {
        // 移除加载提示
        if (document.body.contains(loadingToast)) {
            document.body.removeChild(loadingToast);
        }
        console.error('订单创建失败:', error);
        alert('创建订单失败，请重试');
    });
}

// 添加一些必要的CSS样式
document.addEventListener('DOMContentLoaded', () => {
    // 添加加载动画的样式
    const style = document.createElement('style');
    style.textContent = `
        .loading-toast {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background-color: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            display: flex;
            flex-direction: column;
            align-items: center;
            z-index: 9999;
        }
        .spinner {
            width: 30px;
            height: 30px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
            margin-bottom: 10px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
});