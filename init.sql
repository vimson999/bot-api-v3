
-- 创建数据库（使用UTF8编码）
CREATE DATABASE cappadocia_v1 
    ENCODING 'UTF8' 
    LC_COLLATE 'en_US.UTF-8' 
    LC_CTYPE 'en_US.UTF-8'
    TEMPLATE template0;

-- 创建读写用户（程序专用）
CREATE USER cappadocia_rw WITH 
    PASSWORD 'StrongRwPassword!2024'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;

-- 创建管理用户（运维专用）
CREATE USER cappadocia_man WITH 
    PASSWORD 'StrongManPassword!2024'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;


   CREATE USER cappa_rw WITH 
    PASSWORD 'RWcappaDb!!!2025'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;
   

-- 配置读写用户权限
GRANT CONNECT ON DATABASE cappadocia_v1 TO cappadocia_rw;
GRANT USAGE ON SCHEMA public TO cappadocia_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cappadocia_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cappadocia_rw;


GRANT CONNECT ON DATABASE cappadocia_v1 TO cappa_rw;
GRANT USAGE ON SCHEMA public TO cappa_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cappa_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cappa_rw;


-- 配置管理用户权限
GRANT CONNECT, CREATE ON DATABASE cappadocia_v1 TO cappadocia_man;
GRANT USAGE, CREATE ON SCHEMA public TO cappadocia_man;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public TO cappadocia_man;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO cappadocia_man;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO cappadocia_man;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO cappadocia_man;





-- 创建 log_trace 表
CREATE TABLE log_trace (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_key VARCHAR(36) NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'api',
    app_id VARCHAR(50),
    user_uuid VARCHAR(50),
    user_nickname VARCHAR(50),
    entity_id VARCHAR(100),
    type VARCHAR(50) NOT NULL DEFAULT 'default',
    method_name VARCHAR(100) NOT NULL,
    tollgate VARCHAR(10),
    level VARCHAR(10) NOT NULL DEFAULT 'info' 
        CHECK (level IN ('debug', 'info', 'warning', 'error', 'critical')),
    para JSONB,
    header JSONB,
    body TEXT,
    memo TEXT,
    ip_address VARCHAR(50),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 约束检查
    CONSTRAINT valid_source CHECK (length(source) > 0),
    CONSTRAINT valid_method_name CHECK (length(method_name) > 0),
    CONSTRAINT valid_ip_address CHECK (
        ip_address IS NULL OR 
        ip_address ~ '^(\d{1,3}\.){3}\d{1,3}$' OR 
        ip_address ~ '^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$'
    )
);

-- 创建复合索引
CREATE INDEX idx_log_trace_composite_1 ON log_trace(created_at, source, type);
CREATE INDEX idx_log_trace_composite_2 ON log_trace(user_uuid, created_at);
CREATE INDEX idx_log_trace_composite_3 ON log_trace(app_id, created_at);

-- 精确索引
CREATE INDEX idx_log_trace_trace_key ON log_trace(trace_key);
CREATE INDEX idx_log_trace_source ON log_trace(source);
CREATE INDEX idx_log_trace_app_id ON log_trace(app_id);
CREATE INDEX idx_log_trace_user_uuid ON log_trace(user_uuid);
CREATE INDEX idx_log_trace_user_nickname ON log_trace(user_nickname);
CREATE INDEX idx_log_trace_entity_id ON log_trace(entity_id);
CREATE INDEX idx_log_trace_type ON log_trace(type);
CREATE INDEX idx_log_trace_method_name ON log_trace(method_name);
CREATE INDEX idx_log_trace_level ON log_trace(level);
CREATE INDEX idx_log_trace_created_at ON log_trace(created_at);

-- 创建部分索引，优化查询性能
CREATE INDEX idx_log_trace_error_level ON log_trace(created_at, type, method_name) 
WHERE level IN ('error', 'critical');

-- 创建表注释
COMMENT ON TABLE log_trace IS '系统日志跟踪表，记录API请求、响应和系统事件';

-- 创建列注释
COMMENT ON COLUMN log_trace.id IS '唯一标识符，使用UUID';
COMMENT ON COLUMN log_trace.trace_key IS '跟踪键，用于关联一个完整的请求链';
COMMENT ON COLUMN log_trace.source IS '日志来源，如api、system、background_task等';
COMMENT ON COLUMN log_trace.app_id IS '应用程序ID';
COMMENT ON COLUMN log_trace.user_uuid IS '用户唯一标识';
COMMENT ON COLUMN log_trace.user_nickname IS '用户昵称';
COMMENT ON COLUMN log_trace.entity_id IS '实体ID，可用于关联具体业务对象';
COMMENT ON COLUMN log_trace.type IS '日志类型，如request、response、error等';
COMMENT ON COLUMN log_trace.method_name IS '方法或接口名称';
COMMENT ON COLUMN log_trace.tollgate IS '处理阶段标识';
COMMENT ON COLUMN log_trace.level IS '日志级别';
COMMENT ON COLUMN log_trace.para IS '请求参数，存储为JSON';
COMMENT ON COLUMN log_trace.header IS '请求头信息，存储为JSON';
COMMENT ON COLUMN log_trace.body IS '请求或响应正文';
COMMENT ON COLUMN log_trace.memo IS '备注信息';
COMMENT ON COLUMN log_trace.ip_address IS '客户端IP地址';
COMMENT ON COLUMN log_trace.created_at IS '日志创建时间';




