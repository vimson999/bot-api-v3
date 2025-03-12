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

(venv) v9@v9deMacBook-Pro bot-api-v1 % uvicorn bot_api_v1.app.core.app:create_app --reload --host 0.0.0.0 --port 8000



curl -X POST "http://localhost:8000/api/script/transcribe" \
  -H "Content-Type: application/json" \
  -H "x-source: feishu-sheet" \
  -H "x-app-id: sheet-api" \
  -H "x-user-uuid: user-123456" \
  -H "x-user-nickname: 晓山" \
  -d '{"url": "https://www.youtube.com/shorts/O8GAUEDR0Is"}'