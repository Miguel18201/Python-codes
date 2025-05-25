-- Función para actualizar inventario al realizar ventas
CREATE OR REPLACE FUNCTION actualizar_inventario_venta()
RETURNS TRIGGER AS $$
BEGIN
    -- Actualizar cantidad disponible en inventario general
    UPDATE inventario 
    SET cantidad_disponible = cantidad_disponible - NEW.cantidad
    WHERE id_articulo = NEW.id_articulo;
    
    -- Actualizar distribución en sucursal
    UPDATE distribucion_sucursal
    SET cantidad = cantidad - NEW.cantidad
    WHERE id_articulo = NEW.id_articulo AND id_sucursal = NEW.id_sucursal;
    
    -- Registrar en historial
    INSERT INTO historial_inventario (
        id_articulo, id_sucursal, tipo_movimiento, 
        cantidad, cantidad_anterior, cantidad_nueva,
        motivo, usuario_responsable, id_transaccion
    ) VALUES (
        NEW.id_articulo, NEW.id_sucursal, 'SALIDA',
        NEW.cantidad, 
        (SELECT cantidad FROM distribucion_sucursal WHERE id_articulo = NEW.id_articulo AND id_sucursal = NEW.id_sucursal) + NEW.cantidad,
        (SELECT cantidad FROM distribucion_sucursal WHERE id_articulo = NEW.id_articulo AND id_sucursal = NEW.id_sucursal),
        'VENTA: ' || NEW.guia_envio, 'SISTEMA', NEW.guia_envio
    );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para ventas
CREATE TRIGGER tr_actualizar_inventario_venta
AFTER INSERT ON ventas
FOR EACH ROW
EXECUTE FUNCTION actualizar_inventario_venta();

-- Función para redistribución automática
CREATE OR REPLACE FUNCTION redistribuir_articulo(
    p_id_articulo INTEGER,
    p_id_sucursal_origen INTEGER,
    p_cantidad INTEGER,
    p_usuario VARCHAR(50)
) RETURNS JSON AS $$
DECLARE
    v_resultado JSON;
    v_id_transaccion VARCHAR(50);
BEGIN
    -- Generar ID de transacción
    v_id_transaccion := 'REDIST-' || p_id_articulo || '-' || EXTRACT(EPOCH FROM NOW())::INT;
    
    -- Registrar en consenso distribuido
    INSERT INTO consenso_distribuido (
        id_transaccion, tipo_operacion, datos_operacion,
        total_nodos, nodo_iniciador
    ) VALUES (
        v_id_transaccion, 'REDISTRIBUCION',
        jsonb_build_object(
            'id_articulo', p_id_articulo,
            'id_sucursal_origen', p_id_sucursal_origen,
            'cantidad', p_cantidad
        ),
        (SELECT COUNT(*) FROM sucursales WHERE activa = TRUE),
        p_id_sucursal_origen
    );
    
    -- Aquí iría la lógica de redistribución real
    -- ...
    
    v_resultado := jsonb_build_object(
        'estado', 'PROCESANDO',
        'id_transaccion', v_id_transaccion,
        'mensaje', 'Redistribución iniciada, esperando confirmación de nodos'
    );
    
    RETURN v_resultado;
END;
$$ LANGUAGE plpgsql;