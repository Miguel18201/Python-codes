-- Insertar categorías
INSERT INTO categorias (nombre, descripcion) VALUES 
('Electrónicos', 'Dispositivos electrónicos y gadgets'),
('Oficina', 'Suministros de oficina'),
('Hogar', 'Artículos para el hogar'),
('Alimentos', 'Productos alimenticios');

-- Insertar sucursales (nodos)
INSERT INTO sucursales (nombre, direccion, ciudad, capacidad_maxima, ip, puerto, es_maestro) VALUES
('Sucursal Central', 'Av. Principal 123', 'Lima', 5000, '192.168.1.1', 6001, TRUE),
('Sucursal Norte', 'Calle Norte 456', 'Trujillo', 3000, '192.168.1.1', 6002, FALSE),
('Sucursal Sur', 'Av. Sur 789', 'Arequipa', 3000, '192.168.1.2', 6003, FALSE),
('Sucursal Este', 'Jr. Este 321', 'Huancayo', 2000, '192.168.1.2', 6004, FALSE),
('Sucursal Oeste', 'Av. Oeste 654', 'Chiclayo', 2500, '192.168.1.3', 6005, FALSE),
('Sucursal Centro', 'Calle Central 987', 'Piura', 2000, '192.168.1.3', 6006, FALSE),
('Sucursal Lima Norte', 'Av. Lima 159', 'Lima', 3500, '192.168.1.4', 6007, FALSE),
('Sucursal Lima Sur', 'Av. Sur 753', 'Lima', 3500, '192.168.1.4', 6008, FALSE);

-- Actualizar espacio disponible inicial
UPDATE sucursales SET espacio_disponible = capacidad_maxima;

-- Insertar clientes
INSERT INTO clientes (codigo_cliente, nombre, tipo_documento, numero_documento, direccion, telefono, email, id_sucursal_registro, categoria) VALUES
('CLI-001', 'Empresa ABC SAC', 'RUC', '20123456789', 'Av. Industrial 123', '987654321', 'contacto@empresaabc.com', 1, 'PLATINO'),
('CLI-002', 'Juan Pérez', 'DNI', '12345678', 'Calle Los Pinos 456', '987123456', 'juan.perez@gmail.com', 2, 'ORO'),
('CLI-003', 'Tienda XYZ', 'RUC', '20234567890', 'Jr. Comercial 789', '987321654', 'ventas@xyz.com', 3, 'PLATA'),
('CLI-004', 'María Gómez', 'DNI', '87654321', 'Av. Flores 321', '987654987', 'maria.gomez@hotmail.com', 4, 'NORMAL'),
('CLI-005', 'Distribuidora QRS', 'RUC', '20345678901', 'Calle Mercado 654', '987159357', 'info@qrs.com.pe', 5, 'PLATINO');

-- Insertar artículos
INSERT INTO inventario (codigo_barras, nombre, descripcion, id_categoria, cantidad_total, cantidad_disponible, precio_compra, precio_venta, proveedor, modelo, serie) VALUES
('750123456789', 'Laptop HP EliteBook', 'Laptop i7 16GB RAM 512GB SSD', 1, 50, 50, 2500.00, 3200.00, 'HP Inc.', 'EliteBook 840', 'HP2023L001'),
('750987654321', 'Impresora Epson L380', 'Impresora multifunción tanque de tinta', 1, 30, 30, 800.00, 1200.00, 'Epson', 'L380', 'EPS2023P001'),
('750456123789', 'Escritorio ejecutivo', 'Escritorio de madera 1.60m', 3, 20, 20, 400.00, 650.00, 'Muebles SA', 'Ejec-2023', 'MUE2023E001'),
('750789123456', 'Paquete de papel bond A4', 'Resma 500 hojas 80gr', 2, 100, 100, 25.00, 35.00, 'Paper Corp', 'Bond-80', 'PAP2023A001'),
('750321654987', 'Monitor Dell 24"', 'Monitor Full HD 24 pulgadas', 1, 40, 40, 600.00, 850.00, 'Dell Technologies', 'P2422H', 'DEL2023M001');

-- Distribuir artículos inicialmente
-- Laptop HP EliteBook
INSERT INTO distribucion_sucursal (id_articulo, id_sucursal, cantidad) VALUES
(1, 1, 10), (1, 2, 8), (1, 3, 7), (1, 4, 5), (1, 5, 6), (1, 6, 5), (1, 7, 5), (1, 8, 4);

-- Impresora Epson L380
INSERT INTO distribucion_sucursal (id_articulo, id_sucursal, cantidad) VALUES
(2, 1, 5), (2, 2, 4), (2, 3, 4), (2, 4, 3), (2, 5, 4), (2, 6, 3), (2, 7, 4), (2, 8, 3);

-- Actualizar espacios disponibles
UPDATE sucursales s SET espacio_disponible = s.capacidad_maxima - (
    SELECT COALESCE(SUM(d.cantidad), 0) 
    FROM distribucion_sucursal d 
    WHERE d.id_sucursal = s.id_sucursal
);