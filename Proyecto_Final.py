import socket
import threading
import datetime
import time
import pickle
from concurrent.futures import ThreadPoolExecutor
import random
import psycopg2
from psycopg2 import sql
import logging
import hashlib

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'nodo_inventario.log'),
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

        self._conectar_bd()
        
    def conectar_postgresql(self):
         """Establece conexión con PostgreSQL"""
        try:
            self.db_conn = psycopg2.connect(
                dbname=self.db_config['inventario_distribuido'],
                user=self.db_config['postgres'],
                password=self.db_config['1234'],
                host=self.db_config['localhost'],
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
                    logging.info(f"Nodo {self.id_nodo} recibió mensaje de {mensaje['origen']}: {mensaje['tipo']}")
                    
                    # Procesar mensaje según tipo
                    respuesta = self.procesar_mensaje(mensaje)
                    
                    # Enviar respuesta
                    conn.sendall(pickle.dumps(respuesta))
            except Exception as e:
                logging.error(f"Error manejando conexión: {e}")
                
    def procesar_mensaje(self, mensaje):
        """Procesa diferentes tipos de mensajes"""
        try:
            if mensaje['tipo'] == 'consulta_inventario':
                return self.consultar_inventario()
            elif mensaje['tipo'] == 'consulta_clientes':
                return self.consultar_clientes()
            elif mensaje['tipo'] == 'venta_articulo':
                return self.procesar_venta(mensaje['datos'])
            elif mensaje['tipo'] == 'agregar_articulo':
                return self.agregar_articulo(mensaje['datos'])
            elif mensaje['tipo'] == 'eleccion_maestro':
                return self.participar_eleccion(mensaje)
            elif mensaje['tipo'] == 'confirmacion_maestro':
                self.actualizar_maestro(mensaje['nuevo_maestro'])
                return {'estado': 'ok'}
            elif mensaje['tipo'] == 'redistribuir':
                return self.redistribuir_articulos(mensaje['datos'])
            else:
                return {'estado': 'error', 'mensaje': 'Tipo de mensaje no reconocido'}
        except Exception as e:
            logging.error(f"Error procesando mensaje: {e}")
            return {'estado': 'error', 'mensaje': str(e)}
    
    # Funciones de negocio
    def consultar_inventario(self):
        """Consulta el inventario local"""
        try:
            cur = self.db_conn.cursor()
            cur.execute("""
                SELECT i.id_articulo, i.nombre, i.descripcion, 
                       ds.cantidad, ds.id_sucursal, i.cantidad_total
                FROM inventario i
                JOIN distribucion_sucursal ds ON i.id_articulo = ds.id_articulo
                WHERE ds.id_sucursal = %s
            """, (self.id_nodo,))
            
            inventario = []
            for row in cur.fetchall():
                inventario.append({
                    'id_articulo': row[0],
                    'nombre': row[1],
                    'descripcion': row[2],
                    'cantidad': row[3],
                    'sucursal': row[4],
                    'cantidad_total': row[5]
                })
                
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
        """Procesa una venta con exclusión mutua"""
        with self.lock:
            try:
                # Verificar disponibilidad
                cur = self.db_conn.cursor()
                cur.execute("""
                    SELECT cantidad FROM distribucion_sucursal
                    WHERE id_articulo = %s AND id_sucursal = %s FOR UPDATE
                """, (datos_venta['id_articulo'], self.id_nodo))
                
                cantidad = cur.fetchone()[0]
                if cantidad < datos_venta['cantidad']:
                    return {'estado': 'error', 'mensaje': 'Stock insuficiente'}
                
                # Actualizar inventario
                nueva_cantidad = cantidad - datos_venta['cantidad']
                cur.execute("""
                    UPDATE distribucion_sucursal
                    SET cantidad = %s
                    WHERE id_articulo = %s AND id_sucursal = %s
                """, (nueva_cantidad, datos_venta['id_articulo'], self.id_nodo))
                
                # Actualizar inventario general
                cur.execute("""
                    UPDATE inventario
                    SET cantidad_disponible = cantidad_disponible - %s
                    WHERE id_articulo = %s
                """, (datos_venta['cantidad'], datos_venta['id_articulo']))
                
                # Generar guía de envío
                guia_envio = self.generar_guia_envio(datos_venta)
                
                # Registrar venta
                cur.execute("""
                    INSERT INTO ventas (id_articulo, id_cliente, id_sucursal, guia_envio)
                    VALUES (%s, %s, %s, %s)
                """, (datos_venta['id_articulo'], datos_venta['id_cliente'], self.id_nodo, guia_envio))
                
                self.db_conn.commit()
                
                # Replicar cambios a otros nodos
                self.replicar_venta(datos_venta, nueva_cantidad, guia_envio)
                
                return {'estado': 'ok', 'guia_envio': guia_envio}
            except Exception as e:
                self.db_conn.rollback()
                logging.error(f"Error procesando venta: {e}")
                return {'estado': 'error', 'mensaje': str(e)}
    
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
        """Agrega un nuevo artículo al inventario distribuido"""
        if not self.es_maestro and self.maestro_actual != self.id_nodo:
            # Redirigir al nodo maestro
            return self.redirigir_a_maestro('agregar_articulo', datos_articulo)
            
        with self.lock:
            try:
                cur = self.db_conn.cursor()
                
                # Insertar en inventario general
                cur.execute("""
                    INSERT INTO inventario (nombre, descripcion, cantidad_total, cantidad_disponible)
                    VALUES (%s, %s, %s, %s) RETURNING id_articulo
                """, (datos_articulo['nombre'], datos_articulo['descripcion'], 
                      datos_articulo['cantidad'], datos_articulo['cantidad']))
                
                id_articulo = cur.fetchone()[0]
                
                # Distribuir entre sucursales
                sucursales = self.obtener_sucursales_optimas(datos_articulo['cantidad'])
                for sucursal, cantidad in sucursales.items():
                    cur.execute("""
                        INSERT INTO distribucion_sucursal 
                        (id_articulo, id_sucursal, cantidad, espacio_disponible)
                        VALUES (%s, %s, %s, %s)
                    """, (id_articulo, sucursal, cantidad, 
                          self.calcular_espacio_disponible(sucursal) - cantidad))
                
                self.db_conn.commit()
                
                # Replicar a otros nodos
                self.replicar_nuevo_articulo(id_articulo, datos_articulo, sucursales)
                
                return {'estado': 'ok', 'id_articulo': id_articulo}
            except Exception as e:
                self.db_conn.rollback()
                logging.error(f"Error agregando artículo: {e}")
                return {'estado': 'error', 'mensaje': str(e)}
    
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
    
    def redistribuir_articulos(self, datos_redistribucion):
        """Redistribuye artículos cuando una sucursal falla"""
        if not self.es_maestro and self.maestro_actual != self.id_nodo:
            return {'estado': 'error', 'mensaje': 'Solo el maestro puede redistribuir'}
            
        with self.lock:
            try:
                cur = self.db_conn.cursor()
                
                # Actualizar inventario general
                cur.execute("""
                    UPDATE inventario
                    SET cantidad_disponible = cantidad_disponible - %s
                    WHERE id_articulo = %s
                """, (datos_redistribucion['cantidad'], datos_redistribucion['id_articulo']))
                
                # Distribuir a otras sucursales
                for sucursal, cantidad in datos_redistribucion['nueva_distribucion'].items():
                    cur.execute("""
                        UPDATE distribucion_sucursal
                        SET cantidad = cantidad + %s,
                            espacio_disponible = espacio_disponible - %s
                        WHERE id_articulo = %s AND id_sucursal = %s
                    """, (cantidad, cantidad, datos_redistribucion['id_articulo'], sucursal))
                
                self.db_conn.commit()
                return {'estado': 'ok'}
            except Exception as e:
                self.db_conn.rollback()
                logging.error(f"Error redistribuyendo artículos: {e}")
                return {'estado': 'error', 'mensaje': str(e)}
    
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
        """Interfaz para interactuar con el sistema"""
        while self.activo:
            print("\n=== SISTEMA DE INVENTARIO DISTRIBUIDO ===")
            print(f"Nodo: {self.id_nodo} | {'MAESTRO' if self.es_maestro else 'SUCURSAL'}")
            print("1. Consultar inventario local")
            print("2. Consultar clientes")
            print("3. Vender artículo")
            print("4. Agregar artículo al sistema")
            print("5. Ver estado del sistema")
            print("6. Salir")
            
            opcion = input("Seleccione una opción: ")
            
            try:
                if opcion == '1':
                    self.mostrar_inventario()
                elif opcion == '2':
                    self.mostrar_clientes()
                elif opcion == '3':
                    self.procesar_venta_ui()
                elif opcion == '4':
                    self.agregar_articulo_ui()
                elif opcion == '5':
                    self.mostrar_estado()
                elif opcion == '6':
                    self.activo = False
                    print("Saliendo del sistema...")
                else:
                    print("Opción no válida")
            except Exception as e:
                print(f"Error: {str(e)}")
    
    def mostrar_inventario(self):
        """Muestra el inventario local"""
        inventario = self.consultar_inventario()
        if inventario['estado'] == 'ok':
            print("\n=== INVENTARIO LOCAL ===")
            for item in inventario['inventario']:
                print(f"ID: {item['id_articulo']} | {item['nombre']}")
                print(f"  Descripción: {item['descripcion']}")
                print(f"  Cantidad: {item['cantidad']} | Total sistema: {item['cantidad_total']}")
                print("-" * 40)
        else:
            print(f"Error: {inventario['mensaje']}")
    
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
    
    def procesar_venta_ui(self):
        """Interfaz para procesar una venta"""
        print("\n=== PROCESAR VENTA ===")
        id_articulo = int(input("ID del artículo: "))
        id_cliente = int(input("ID del cliente: "))
        cantidad = int(input("Cantidad a vender: "))
        
        resultado = self.procesar_venta({
            'id_articulo': id_articulo,
            'id_cliente': id_cliente,
            'cantidad': cantidad
        })
        
        if resultado['estado'] == 'ok':
            print(f"\n✅ Venta realizada correctamente")
            print(f"Guía de envío: {resultado['guia_envio']}")
        else:
            print(f"\n❌ Error: {resultado['mensaje']}")
    
    def agregar_articulo_ui(self):
        """Interfaz para agregar un nuevo artículo"""
        print("\n=== AGREGAR ARTÍCULO ===")
        nombre = input("Nombre del artículo: ")
        descripcion = input("Descripción: ")
        cantidad = int(input("Cantidad inicial: "))
        
        resultado = self.agregar_articulo({
            'nombre': nombre,
            'descripcion': descripcion,
            'cantidad': cantidad
        })
        
        if resultado['estado'] == 'ok':
            print(f"\n✅ Artículo agregado correctamente")
            print(f"ID asignado: {resultado['id_articulo']}")
        else:
            print(f"\n❌ Error: {resultado['mensaje']}")
    
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
   try:
        nodo = NodoInventario(
            id_nodo=config['id_nodo'],
            puerto=config['puerto'],
            nodos_conocidos=config['nodos_conocidos'],
            db_config=config['db_config'],  # Configuración de BD requerida
            es_maestro=config.get('es_maestro', False)
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
except Exception as e:
        logging.error(f"Error al iniciar nodo: {e}")


if __name__ == "__main__":
    # Configuración de los nodos (debe ser consistente en todos)
    TODOS_NODOS = {
        1: ('192.168.116.133', 5001),
        2: ('192.168.116.128', 5002),
        3: ('192.168.116.134', 5003),
        4: ('192.168.1.2', 5004),
        5: ('192.168.1.3', 5005),
        6: ('192.168.1.3', 5006),
        7: ('192.168.1.4', 5007),
        8: ('192.168.1.4', 5008)
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
        }, 
       'db_config': {  
            'database': 'inventario_distribuido',
            'user': 'nodo_inventario',
            'password': '1234',  # Debe coincidir con PostgreSQL
            'host': 'localhost',
            'port': 5432
        }
    }
    
    # Configurar PostgreSQL antes de iniciar
    print("\nConfigurando PostgreSQL...")
    print("Asegúrese de que:")
    print("1. PostgreSQL esté instalado y corriendo")
    print("2. Exista una base de datos llamada 'inventario_distribuido'")
    print("3. Las credenciales en el código sean correctas")
    
    iniciar_nodo_inventario(config)
