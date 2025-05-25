-- Tabla de sucursales/nodos
CREATE TABLE sucursales (
    id_sucursal SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    direccion TEXT NOT NULL,
    ciudad VARCHAR(50) NOT NULL,
    capacidad_maxima INTEGER DEFAULT 1000,
    espacio_disponible INTEGER,
    ip VARCHAR(15) NOT NULL,
    puerto INTEGER NOT NULL,
    es_maestro BOOLEAN DEFAULT FALSE,
    ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activa BOOLEAN DEFAULT TRUE
);

-- Tabla de categorías de artículos
CREATE TABLE categorias (
    id_categoria SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    descripcion TEXT
);

-- Tabla principal de inventario
CREATE TABLE inventario (
    id_articulo SERIAL PRIMARY KEY,
    codigo_barras VARCHAR(20) UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    id_categoria INTEGER REFERENCES categorias(id_categoria),
    cantidad_total INTEGER NOT NULL DEFAULT 0,
    cantidad_disponible INTEGER NOT NULL DEFAULT 0,
    precio_compra DECIMAL(10,2),
    precio_venta DECIMAL(10,2),
    fecha_ingreso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    proveedor VARCHAR(100),
    modelo VARCHAR(50),
    serie VARCHAR(50),
    UNIQUE(nombre, modelo, serie)
);

-- Tabla de distribución por sucursal
CREATE TABLE distribucion_sucursal (
    id_distribucion SERIAL PRIMARY KEY,
    id_articulo INTEGER NOT NULL REFERENCES inventario(id_articulo),
    id_sucursal INTEGER NOT NULL REFERENCES sucursales(id_sucursal),
    cantidad INTEGER NOT NULL DEFAULT 0,
    cantidad_minima INTEGER DEFAULT 5,
    ubicacion VARCHAR(50),
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_articulo, id_sucursal)
);

-- Tabla de clientes
CREATE TABLE clientes (
    id_cliente SERIAL PRIMARY KEY,
    codigo_cliente VARCHAR(20) UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    tipo_documento VARCHAR(10) CHECK (tipo_documento IN ('DNI', 'RUC', 'CEDULA', 'PASAPORTE')),
    numero_documento VARCHAR(20) UNIQUE,
    direccion TEXT,
    telefono VARCHAR(20),
    email VARCHAR(100),
    id_sucursal_registro INTEGER REFERENCES sucursales(id_sucursal),
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    categoria VARCHAR(20) DEFAULT 'NORMAL' CHECK (categoria IN ('NORMAL', 'PLATA', 'ORO', 'PLATINO'))
);

-- Tabla de ventas
CREATE TABLE ventas (
    id_venta SERIAL PRIMARY KEY,
    id_articulo INTEGER NOT NULL REFERENCES inventario(id_articulo),
    id_cliente INTEGER REFERENCES clientes(id_cliente),
    id_sucursal INTEGER NOT NULL REFERENCES sucursales(id_sucursal),
    cantidad INTEGER NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    descuento DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) GENERATED ALWAYS AS (cantidad * precio_unitario - descuento) STORED,
    fecha_venta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    guia_envio VARCHAR(100) UNIQUE NOT NULL,
    estado VARCHAR(20) DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE', 'DESPACHADO', 'ENTREGADO', 'CANCELADO')),
    metodo_pago VARCHAR(20) CHECK (metodo_pago IN ('EFECTIVO', 'TARJETA', 'TRANSFERENCIA', 'CREDITO'))
);

-- Tabla de historial de movimientos
CREATE TABLE historial_inventario (
    id_movimiento SERIAL PRIMARY KEY,
    id_articulo INTEGER NOT NULL REFERENCES inventario(id_articulo),
    id_sucursal INTEGER REFERENCES sucursales(id_sucursal),
    tipo_movimiento VARCHAR(20) NOT NULL CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA', 'AJUSTE', 'TRANSFERENCIA')),
    cantidad INTEGER NOT NULL,
    cantidad_anterior INTEGER,
    cantidad_nueva INTEGER,
    motivo TEXT,
    fecha_movimiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_responsable VARCHAR(50),
    id_transaccion VARCHAR(50)
);

-- Tabla para registro de consenso distribuido
CREATE TABLE consenso_distribuido (
    id_transaccion VARCHAR(50) PRIMARY KEY,
    tipo_operacion VARCHAR(50) NOT NULL,
    datos_operacion JSONB NOT NULL,
    nodos_confirmados INTEGER DEFAULT 1,
    total_nodos INTEGER NOT NULL,
    estado VARCHAR(20) DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE', 'CONFIRMADO', 'RECHAZADO', 'ERROR')),
    fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_confirmacion TIMESTAMP,
    nodo_iniciador INTEGER REFERENCES sucursales(id_sucursal)
);

-- Índices para mejorar performance
CREATE INDEX idx_inventario_nombre ON inventario(nombre);
CREATE INDEX idx_distribucion_articulo ON distribucion_sucursal(id_articulo);
CREATE INDEX idx_distribucion_sucursal ON distribucion_sucursal(id_sucursal);
CREATE INDEX idx_ventas_fecha ON ventas(fecha_venta);
CREATE INDEX idx_ventas_guia ON ventas(guia_envio);
CREATE INDEX idx_historial_articulo ON historial_inventario(id_articulo);
CREATE INDEX idx_historial_fecha ON historial_inventario(fecha_movimiento);