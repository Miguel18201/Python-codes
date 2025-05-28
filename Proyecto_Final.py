import socket
import threading
import datetime
import time
import pickle
import psycopg2
from psycopg2 import sql, errors
import logging
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nodo_inventario.log'),
        logging.StreamHandler()
    ]
)

class NodoInventario:
    def __init__(self, id_nodo, puerto, nodos_conocidos, db_config, es_maestro=False):
        self.id_nodo = id_nodo
        self.puerto = puerto
        self.nodos_conocidos = nodos_conocidos
        self.es_maestro = es_maestro
        self.maestro_actual = 1
        self.activo = True
        self.lock = threading.Lock()
        self.db_config = db_config
        self.db_conn = None
        
        # Conectar a PostgreSQL al iniciar
        self._conectar_bd()

    def _conectar_bd(self):
        """Establece conexión con PostgreSQL"""
        try:
            self.db_conn = psycopg2.connect(
                dbname=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                host=self.db_config['host'],
                port=self.db_config.get('port', 5432)
            )
            logging.info("Conexión a PostgreSQL establecida")
        except Exception as e:
            logging.error(f"Error conectando a PostgreSQL: {e}")
            self.db_conn = None
    
    def inicializar_bd(self):
        if not self.db_conn:
            return
            
        try:
            cur = self.db_conn.cursor()
            
            # Tabla de inventario
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inventario (
                    id_articulo SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    descripcion TEXT,
                    cantidad_total INTEGER NOT NULL,
                    cantidad_disponible INTEGER NOT NULL,
                    sucursal_asignada INTEGER,
                    serie VARCHAR(50),
                    fecha_ingreso TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de distribución por sucursal
            cur.execute("""
                CREATE TABLE IF NOT EXISTS distribucion_sucursal (
                    id_distribucion SERIAL PRIMARY KEY,
                    id_articulo INTEGER REFERENCES inventario(id_articulo),
                    id_sucursal INTEGER NOT NULL,
                    cantidad INTEGER NOT NULL,
                    capacidad_maxima INTEGER DEFAULT 100,
                    espacio_disponible INTEGER,
                    ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de clientes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clientes (
                    id_cliente SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    direccion TEXT NOT NULL,
                    telefono VARCHAR(20),
                    email VARCHAR(100),
                    sucursal_registro INTEGER NOT NULL,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de ventas
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ventas (
                    id_venta SERIAL PRIMARY KEY,
                    id_articulo INTEGER REFERENCES inventario(id_articulo),
                    id_cliente INTEGER REFERENCES clientes(id_cliente),
                    id_sucursal INTEGER NOT NULL,
                    fecha_venta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    guia_envio VARCHAR(100) UNIQUE NOT NULL,
                    estado VARCHAR(20) DEFAULT 'pendiente'
                )
            """)
            
            self.db_conn.commit()
            logging.info("Estructura de BD inicializada correctamente")
            
        except Exception as e:
            logging.error(f"Error inicializando BD: {e}")
            self.db_conn.rollback()
            
    def servidor(self):
        """Escucha conexiones entrantes"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', self.puerto))
                s.listen()
                logging.info(f"Nodo {self.id_nodo} escuchando en puerto {self.puerto}")
                
                while self.activo:
                    conn, addr = s.accept()
                    threading.Thread(target=self.manejar_conexion, args=(conn,)).start()
            except Exception as e:
                logging.error(f"Error en servidor: {e}")
                self.activo = False
    
    def manejar_conexion(self, conn):
       """Maneja una conexión entrante"""
       with conn:
           try:
               data = conn.recv(4096)
               if data:
                   mensaje = pickle.loads(data)
                   respuesta = self.procesar_mensaje(mensaje)
                   conn.sendall(pickle.dumps(respuesta))
           except Exception as e:
               logging.error(f"Error manejando conexión: {e}")
                
    def procesar_mensaje(self, mensaje):
        """Procesa mensajes según tipo"""
        try:
            if mensaje['tipo'] == 'consulta_inventario':
                return self.consultar_inventario()
            elif mensaje['tipo'] == 'venta_articulo':
                return self.procesar_venta(mensaje['datos'])
            elif mensaje['tipo'] == 'agregar_articulo':
                return self.agregar_articulo(mensaje['datos'])
            else:
                return {'estado': 'error', 'mensaje': 'Tipo no válido'}
        except Exception as e:
            logging.error(f"Error procesando mensaje: {e}")
            return {'estado': 'error', 'mensaje': str(e)}
    
    # Funciones de negocio
    def consultar_inventario(self):
        """Consulta inventario local"""
        if not self.db_conn:
            return {'estado': 'error', 'mensaje': 'BD no conectada'}
        
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    SELECT i.id_articulo, i.nombre, i.descripcion, 
                           ds.cantidad, i.precio_venta
                    FROM inventario i
                    JOIN distribucion_sucursal ds ON i.id_articulo = ds.id_articulo
                    WHERE ds.id_sucursal = %s
                """, (self.id_nodo,))
                
                inventario = [{
                    'id': row[0],
                    'nombre': row[1],
                    'descripcion': row[2],
                    'cantidad': row[3],
                    'precio': float(row[4])
                } for row in cur.fetchall()]
                
                return {'estado': 'ok', 'inventario': inventario}
        except Exception as e:
            logging.error(f"Error consultando inventario: {e}")
            return {'estado': 'error', 'mensaje': str(e)}
    
    def consultar_clientes(self):
        """Consulta los clientes (distribuido)"""
        try:
            cur = self.db_conn.cursor()
            cur.execute("SELECT * FROM clientes")
            
            clientes = []
            for row in cur.fetchall():
                clientes.append({
                    'id_cliente': row[0],
                    'nombre': row[1],
                    'direccion': row[2],
                    'telefono': row[3],
                    'email': row[4],
                    'sucursal_registro': row[5]
                })
                
            return {'estado': 'ok', 'clientes': clientes}
        except Exception as e:
            logging.error(f"Error consultando clientes: {e}")
            return {'estado': 'error', 'mensaje': str(e)}
    
    def procesar_venta(self, datos_venta):
        """Procesa una venta con transacción"""
        if not self.db_conn:
            return {'estado': 'error', 'mensaje': 'BD no conectada'}
        
        try:
            with self.db_conn.cursor() as cur:
                # Iniciar transacción
                self.db_conn.autocommit = False
                
                # 1. Verificar stock
                cur.execute("""
                    SELECT cantidad FROM distribucion_sucursal
                    WHERE id_articulo = %s AND id_sucursal = %s FOR UPDATE
                """, (datos_venta['id_articulo'], self.id_nodo))
                stock = cur.fetchone()[0]
                
                if stock < datos_venta['cantidad']:
                    raise ValueError("Stock insuficiente")
                
                # 2. Obtener precio
                cur.execute("""
                    SELECT precio_venta FROM inventario
                    WHERE id_articulo = %s
                """, (datos_venta['id_articulo'],))
                precio = cur.fetchone()[0]
                
                # 3. Registrar venta
                guia = self._generar_guia()
                cur.execute("""
                    INSERT INTO ventas (
                        id_articulo, id_cliente, id_sucursal,
                        cantidad, precio_unitario, guia_envio
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    datos_venta['id_articulo'],
                    datos_venta['id_cliente'],
                    self.id_nodo,
                    datos_venta['cantidad'],
                    precio,
                    guia
                ))
                
                # 4. Actualizar stock
                cur.execute("""
                    UPDATE distribucion_sucursal
                    SET cantidad = cantidad - %s
                    WHERE id_articulo = %s AND id_sucursal = %s
                """, (datos_venta['cantidad'], datos_venta['id_articulo'], self.id_nodo))
                
                self.db_conn.commit()
                return {'estado': 'ok', 'guia': guia}
                
        except Exception as e:
            self.db_conn.rollback()
            logging.error(f"Error en venta: {e}")
            return {'estado': 'error', 'mensaje': str(e)}
        finally:
            self.db_conn.autocommit = True 
    
    def generar_guia_envio(self, datos_venta):
        """Genera un ID único para la guía de envío"""
        cadena = f"{datos_venta['id_articulo']}-{self.id_nodo}-{datos_venta['id_cliente']}-{time.time()}"
        return hashlib.sha256(cadena.encode()).hexdigest()[:20].upper()
    
    def replicar_venta(self, datos_venta, nueva_cantidad, guia_envio):
        """Replica la venta a otros nodos para consistencia"""
        mensaje = {
            'tipo': 'actualizar_inventario',
            'datos': {
                'id_articulo': datos_venta['id_articulo'],
                'id_sucursal': self.id_nodo,
                'nueva_cantidad': nueva_cantidad,
                'guia_envio': guia_envio,
                'id_cliente': datos_venta['id_cliente']
            }
        }
        
        for nodo_id, (ip, puerto) in self.nodos_conocidos.items():
            if nodo_id != self.id_nodo:
                try:
                    self.enviar_mensaje(nodo_id, mensaje)
                except Exception as e:
                    logging.error(f"Error replicando a nodo {nodo_id}: {e}")
    
    def agregar_articulo(self, datos_articulo):
        """Agrega un artículo nuevo con distribución automática"""
        if not self.db_conn:
            return {'estado': 'error', 'mensaje': 'BD no conectada'}
        
        try:
            with self.db_conn.cursor() as cur:
                self.db_conn.autocommit = False
                
                # 1. Insertar en inventario
                cur.execute("""
                    INSERT INTO inventario (
                        nombre, descripcion, cantidad_total,
                        cantidad_disponible, precio_venta
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id_articulo
                """, (
                    datos_articulo['nombre'],
                    datos_articulo['descripcion'],
                    datos_articulo['cantidad'],
                    datos_articulo['cantidad'],
                    datos_articulo.get('precio_venta', 0.0)
                ))
                id_articulo = cur.fetchone()[0]
                
                # 2. Distribuir en sucursales
                sucursales = self._distribuir_articulo(id_articulo, datos_articulo['cantidad'])
                for sucursal, cantidad in sucursales.items():
                    cur.execute("""
                        INSERT INTO distribucion_sucursal (
                            id_articulo, id_sucursal, cantidad
                        ) VALUES (%s, %s, %s)
                    """, (id_articulo, sucursal, cantidad))
                
                self.db_conn.commit()
                return {'estado': 'ok', 'id_articulo': id_articulo}
                
        except Exception as e:
            self.db_conn.rollback()
            logging.error(f"Error agregando artículo: {e}")
            return {'estado': 'error', 'mensaje': str(e)}
        finally:
            self.db_conn.autocommit = True
    
    def obtener_sucursales_optimas(self, cantidad_total):
        """Distribuye el artículo entre sucursales con más espacio"""
        try:
            cur = self.db_conn.cursor()
            cur.execute("""
                SELECT id_sucursal, espacio_disponible 
                FROM distribucion_sucursal
                GROUP BY id_sucursal, espacio_disponible
                ORDER BY espacio_disponible DESC
            """)
            
            sucursales = {}
            resultados = cur.fetchall()
            total_espacio = sum(row[1] for row in resultados)
            
            for row in resultados:
                proporcion = row[1] / total_espacio if total_espacio > 0 else 1/len(resultados)
                sucursales[row[0]] = int(cantidad_total * proporcion)
                
            # Ajustar redondeo
            diferencia = cantidad_total - sum(sucursales.values())
            if diferencia != 0:
                sucursales[resultados[0][0]] += diferencia
                
            return sucursales
        except Exception as e:
            logging.error(f"Error calculando distribución: {e}")
            # Distribución equitativa por defecto
            return {nodo_id: cantidad_total//len(self.nodos_conocidos) 
                    for nodo_id in self.nodos_conocidos if nodo_id != self.id_nodo}
    
    def calcular_espacio_disponible(self, id_sucursal):
        """Calcula el espacio disponible en una sucursal"""
        try:
            cur = self.db_conn.cursor()
            cur.execute("""
                SELECT capacidad_maxima - SUM(cantidad)
                FROM distribucion_sucursal
                WHERE id_sucursal = %s
                GROUP BY capacidad_maxima
            """, (id_sucursal,))
            
            return cur.fetchone()[0] or 100  # Valor por defecto si no hay registros
        except Exception as e:
            logging.error(f"Error calculando espacio: {e}")
            return 100
    
    def replicar_nuevo_articulo(self, id_articulo, datos_articulo, distribucion):
        """Replica el nuevo artículo a todos los nodos"""
        mensaje = {
            'tipo': 'nuevo_articulo',
            'datos': {
                'id_articulo': id_articulo,
                'articulo': datos_articulo,
                'distribucion': distribucion
            }
        }
        
        for nodo_id, (ip, puerto) in self.nodos_conocidos.items():
            if nodo_id != self.id_nodo:
                try:
                    self.enviar_mensaje(nodo_id, mensaje)
                except Exception as e:
                    logging.error(f"Error replicando a nodo {nodo_id}: {e}")
    
    def _distribuir_articulo(self, id_articulo, cantidad_total):
       """Distribuye un artículo entre sucursales"""
       try:
           with self.db_conn.cursor() as cur:
               cur.execute("""
                   SELECT id_sucursal, capacidad_maxima - COALESCE(SUM(cantidad), 0) as espacio
                   FROM distribucion_sucursal
                   GROUP BY id_sucursal, capacidad_maxima
                   ORDER BY espacio DESC
               """)
               
               sucursales = {}
               resultados = cur.fetchall()
               total_espacio = max(sum(row[1] for row in resultados), 1)
               
               for row in resultados:
                   proporcion = row[1] / total_espacio
                   sucursales[row[0]] = int(cantidad_total * proporcion)
               
               # Ajustar redondeo
               diferencia = cantidad_total - sum(sucursales.values())
               if diferencia != 0:
                   sucursales[resultados[0][0]] += diferencia
               
               return sucursales
       except Exception as e:
           logging.error(f"Error en distribución: {e}")
           return {self.id_nodo: cantidad_total}  # Fallback a nodo actual

    
    # Funciones para elección de maestro
    def verificar_maestro(self):
        """Verifica si el nodo maestro está activo"""
        if self.maestro_actual == self.id_nodo:
            return True
            
        try:
            respuesta = self.enviar_mensaje(self.maestro_actual, {'tipo': 'ping'})
            return respuesta is not None
        except:
            return False
    
    def iniciar_eleccion(self):
        """Inicia una elección de nodo maestro"""
        if self.eleccion_en_curso:
            return
            
        self.eleccion_en_curso = True
        logging.info(f"Nodo {self.id_nodo} iniciando elección de maestro")
        
        # Enviar mensaje de elección a nodos con ID mayor
        mayores = [nodo_id for nodo_id in self.nodos_conocidos if nodo_id > self.id_nodo]
        
        if not mayores:
            # Este nodo es el de mayor ID, se convierte en maestro
            self.convertirse_en_maestro()
            return
            
        respuestas = []
        for nodo_id in mayores:
            try:
                respuesta = self.enviar_mensaje(nodo_id, {
                    'tipo': 'eleccion_maestro',
                    'iniciador': self.id_nodo
                })
                if respuesta and respuesta.get('estado') == 'ok':
                    respuestas.append(True)
            except:
                continue
                
        if not any(respuestas):
            # Ningún nodo mayor respondió, este nodo se convierte en maestro
            self.convertirse_en_maestro()
    
    def participar_eleccion(self, mensaje):
        """Participa en una elección de maestro"""
        if mensaje['iniciador'] < self.id_nodo:
            # Este nodo tiene mayor ID, toma el control
            self.iniciar_eleccion()
            return {'estado': 'ok', 'tomando_control': True}
        
        return {'estado': 'ok', 'tomando_control': False}
    
    def convertirse_en_maestro(self):
        """Convierte este nodo en el maestro"""
        self.es_maestro = True
        self.maestro_actual = self.id_nodo
        self.eleccion_en_curso = False
        logging.info(f"Nodo {self.id_nodo} es ahora el maestro")
        
        # Notificar a todos los nodos
        for nodo_id, (ip, puerto) in self.nodos_conocidos.items():
            if nodo_id != self.id_nodo:
                try:
                    self.enviar_mensaje(nodo_id, {
                        'tipo': 'confirmacion_maestro',
                        'nuevo_maestro': self.id_nodo
                    })
                except Exception as e:
                    logging.error(f"Error notificando a nodo {nodo_id}: {e}")
    
    def actualizar_maestro(self, nuevo_maestro):
        """Actualiza la referencia al nodo maestro"""
        self.maestro_actual = nuevo_maestro
        self.es_maestro = (nuevo_maestro == self.id_nodo)
        logging.info(f"Nodo {self.id_nodo} reconoce a {nuevo_maestro} como maestro")
    
    # Funciones de red
    def enviar_mensaje(self, destino_id, mensaje):
        """Envía un mensaje a otro nodo"""
        if destino_id not in self.nodos_conocidos:
            logging.error(f"Nodo {destino_id} desconocido")
            return None
        
        ip, puerto = self.nodos_conocidos[destino_id]
        mensaje['origen'] = self.id_nodo
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((ip, puerto))
                s.sendall(pickle.dumps(mensaje))
                
                # Esperar respuesta
                data = s.recv(4096)
                if data:
                    return pickle.loads(data)
                return None
        except Exception as e:
            logging.error(f"Error enviando mensaje a nodo {destino_id}: {e}")
            return None
    
    def redirigir_a_maestro(self, tipo, datos):
        """Redirige una operación al nodo maestro"""
        try:
            respuesta = self.enviar_mensaje(self.maestro_actual, {
                'tipo': tipo,
                'datos': datos
            })
            return respuesta if respuesta else {'estado': 'error', 'mensaje': 'No se pudo contactar al maestro'}
        except Exception as e:
            logging.error(f"Error redirigiendo al maestro: {e}")
            return {'estado': 'error', 'mensaje': str(e)}
    
    # Interfaz de usuario
    def interfaz_usuario(self):
        """Menú interactivo"""
        while self.activo:
            print("\n=== SISTEMA DE INVENTARIO ===")
            print(f"Nodo {self.id_nodo} | {'MAESTRO' if self.es_maestro else 'SLAVE'}")
            print("1. Consultar inventario")
            print("2. Vender artículo")
            print("3. Agregar artículo")
            print("4. Salir")
            
            try:
                opcion = input("Seleccione: ")
                
                if opcion == '1':
                    self._mostrar_inventario()
                elif opcion == '2':
                    self._procesar_venta_ui()
                elif opcion == '3':
                    self._agregar_articulo_ui()
                elif opcion == '4':
                    self.activo = False
                else:
                    print("Opción no válida")
                    
            except Exception as e:
                print(f"Error: {str(e)}")
    
    def _mostrar_inventario(self):
        """Muestra inventario local"""
        resultado = self.consultar_inventario()
        if resultado['estado'] == 'ok':
            print("\n=== INVENTARIO ===")
            for item in resultado['inventario']:
                print(f"ID: {item['id']} | {item['nombre']}")
                print(f"  Stock: {item['cantidad']} | Precio: ${item['precio']:.2f}")
                print("-" * 40)
        else:
            print(f"Error: {resultado['mensaje']}")

    
    def mostrar_clientes(self):
        """Muestra la lista de clientes"""
        clientes = self.consultar_clientes()
        if clientes['estado'] == 'ok':
            print("\n=== CLIENTES REGISTRADOS ===")
            for cliente in clientes['clientes']:
                print(f"ID: {cliente['id_cliente']} | {cliente['nombre']}")
                print(f"  Tel: {cliente['telefono']} | Email: {cliente['email']}")
                print(f"  Dirección: {cliente['direccion']}")
                print(f"  Sucursal registro: {cliente['sucursal_registro']}")
                print("-" * 40)
        else:
            print(f"Error: {clientes['mensaje']}")
    
    def _procesar_venta_ui(self):
        """Interfaz para ventas"""
        print("\n=== VENDER ARTÍCULO ===")
        try:
            id_articulo = int(input("ID Artículo: "))
            id_cliente = int(input("ID Cliente: "))
            cantidad = int(input("Cantidad: "))
            
            resultado = self.procesar_venta({
                'id_articulo': id_articulo,
                'id_cliente': id_cliente,
                'cantidad': cantidad
            })
            
            if resultado['estado'] == 'ok':
                print(f"\n✅ Venta registrada. Guía: {resultado['guia']}")
            else:
                print(f"\n❌ Error: {resultado['mensaje']}")
                
        except ValueError:
            print("Error: Ingresa valores numéricos")
    
    def _agregar_articulo_ui(self):
        """Interfaz para agregar artículos"""
        print("\n=== AGREGAR ARTÍCULO ===")
        try:
            nombre = input("Nombre: ")
            descripcion = input("Descripción: ")
            cantidad = int(input("Cantidad inicial: "))
            precio = float(input("Precio de venta: "))
            
            resultado = self.agregar_articulo({
                'nombre': nombre,
                'descripcion': descripcion,
                'cantidad': cantidad,
                'precio_venta': precio
            })
            
            if resultado['estado'] == 'ok':
                print(f"\n✅ Artículo agregado (ID: {resultado['id_articulo']})")
            else:
                print(f"\n❌ Error: {resultado['mensaje']}")
                
        except ValueError:
            print("Error: Ingresa valores válidos")
    
    def mostrar_estado(self):
        """Muestra el estado del sistema"""
        print("\n=== ESTADO DEL SISTEMA ===")
        print(f"Nodo actual: {self.id_nodo}")
        print(f"Rol: {'MAESTRO' if self.es_maestro else 'SUCURSAL'}")
        print(f"Maestro actual: {self.maestro_actual}")
        print(f"Nodos conocidos: {len(self.nodos_conocidos)}")
        
        # Verificar conexión con otros nodos
        print("\nEstado de nodos:")
        for nodo_id, (ip, puerto) in self.nodos_conocidos.items():
            estado = "✅ ACTIVO" if self.verificar_conexion(nodo_id) else "❌ INACTIVO"
            print(f"Nodo {nodo_id}: {estado}")
    
    def verificar_conexion(self, nodo_id):
        """Verifica si un nodo está activo"""
        if nodo_id == self.id_nodo:
            return True
            
        try:
            respuesta = self.enviar_mensaje(nodo_id, {'tipo': 'ping'})
            return respuesta is not None
        except:
            return False

def iniciar_nodo_inventario(config):
    """Inicia un nodo del sistema de inventario"""
    nodo = NodoInventario(
        id_nodo=config['id'],
        puerto=config['puerto'],
        nodos_conocidos=config['nodos_conocidos'],
        es_maestro=(config['id'] == 1)  # El nodo 1 es maestro inicial
    ) 
    # Iniciar servidor en segundo plano
    threading.Thread(target=nodo.servidor, daemon=True).start()
    
    # Pequeña pausa para asegurar que el servidor esté listo
    time.sleep(1)
    
    # Verificar si el maestro está activo
    if not nodo.verificar_maestro() and config['id'] != 1:
        logging.warning("Maestro no responde, iniciando elección...")
        nodo.iniciar_eleccion()
    
    # Iniciar interfaz de usuario
    nodo.interfaz_usuario()

if __name__ == "__main__":
    # Configuración de los nodos (debe ser consistente en todos)
    TODOS_NODOS = {
        1: ('192.168.1.1', 6001),
        2: ('192.168.1.1', 6002),
        3: ('192.168.1.2', 6003),
        4: ('192.168.1.2', 6004),
        5: ('192.168.1.3', 6005),
        6: ('192.168.1.3', 6006),
        7: ('192.168.1.4', 6007),
        8: ('192.168.1.4', 6008)
    }
    
    print("=== SISTEMA DE INVENTARIO DISTRIBUIDO ===")
    print("Nodos disponibles:", ", ".join(str(id) for id in TODOS_NODOS))
    id_nodo = int(input("Ingrese el número de nodo a iniciar (1-8): "))
    
    if id_nodo not in TODOS_NODOS:
        print("ID de nodo inválido")
        exit(1)
    
    # Configuración para este nodo
    config = {
        'id': id_nodo,
        'puerto': TODOS_NODOS[id_nodo][1],
        'nodos_conocidos': TODOS_NODOS
    }
    
    # Configurar PostgreSQL antes de iniciar
    print("\nConfigurando PostgreSQL...")
    print("Asegúrese de que:")
    print("1. PostgreSQL esté instalado y corriendo")
    print("2. Exista una base de datos llamada 'inventario_distribuido'")
    print("3. Las credenciales en el código sean correctas")
    
    iniciar_nodo_inventario(config)
