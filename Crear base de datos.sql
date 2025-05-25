-- Crear base de datos
CREATE DATABASE inventario_distribuido WITH 
    ENCODING = 'UTF8' 
    LC_COLLATE = 'en_US.UTF-8' 
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Crear usuario
CREATE USER nodo_inventario WITH PASSWORD 'PasswordSeguro123';

-- Privilegios
GRANT ALL PRIVILEGES ON DATABASE inventario_distribuido TO nodo_inventario;

-- Ajustar parámetros (opcional para mejor performance)
ALTER SYSTEM SET max_connections = 100;
ALTER SYSTEM SET shared_buffers = '1GB';
ALTER SYSTEM SET effective_cache_size = '3GB';