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
and name = 'test_signature_app'
order by created_at desc 
limit 100;





