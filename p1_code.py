import socket
import threading
import datetime
import pickle
import time

class NodoMaestro:
    def __init__(self, puerto, nodos_sucursales):
        self.puerto = puerto
        self.nodos_sucursales = nodos_sucursales  # {id: (ip, puerto)}
        self.inventario_global = {
            'A001': 100,
            'A002': 200,
            'A003': 150
        }
        self.locks_articulos = {}  # articulo_id: id_sucursal_que_lo_uso
        self.lock = threading.Lock()

    def servidor(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.puerto))
            s.listen()
            print(f"Maestro escuchando en puerto {self.puerto}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.manejar_conexion, args=(conn,)).start()

    def manejar_conexion(self, conn):
        with conn:
            data = b''
            while True:
                parte = conn.recv(4096)
                if not parte:
                    break
                data += parte
            if not data:
                return
            mensaje = pickle.loads(data)
            tipo = mensaje.get('tipo')
            respuesta = {}

            if tipo == 'solicitar_inventario':
                # Envía inventario completo (podrías enviar solo parte o actualizaciones)
                respuesta = {'tipo': 'inventario', 'inventario': self.inventario_global}

            elif tipo == 'bloquear_articulo':
                articulo = mensaje.get('articulo_id')
                sucursal = mensaje.get('origen')
                with self.lock:
                    if articulo not in self.locks_articulos:
                        self.locks_articulos[articulo] = sucursal
                        respuesta = {'tipo': 'lock_confirmado', 'articulo_id': articulo}
                    else:
                        respuesta = {'tipo': 'lock_denegado', 'articulo_id': articulo}

            elif tipo == 'liberar_articulo':
                articulo = mensaje.get('articulo_id')
                sucursal = mensaje.get('origen')
                with self.lock:
                    if self.locks_articulos.get(articulo) == sucursal:
                        del self.locks_articulos[articulo]
                        respuesta = {'tipo': 'unlock_confirmado', 'articulo_id': articulo}
                    else:
                        respuesta = {'tipo': 'unlock_denegado', 'articulo_id': articulo}

            elif tipo == 'actualizar_inventario':
                # Una sucursal informa que vendió X cantidad y el maestro actualiza
                articulo = mensaje.get('articulo_id')
                cantidad = mensaje.get('cantidad')
                with self.lock:
                    if articulo in self.inventario_global:
                        self.inventario_global[articulo] -= cantidad
                respuesta = {'tipo': 'actualizacion_recibida'}

            elif tipo == 'consultar_clientes':
                # Para simplicidad, maestro no maneja clientes, solo reenvía consulta a sucursales
                respuesta = {'tipo': 'no_implementado'}

            # Envía respuesta
            conn.sendall(pickle.dumps(respuesta))

    def distribuir_inventario(self):
        # Ejemplo simple: al inicio o cada cierto tiempo se envía inventario a sucursales
        for id_suc, (ip, puerto) in self.nodos_sucursales.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, puerto))
                    mensaje = {'tipo': 'actualizar_inventario', 'inventario': self.inventario_global}
                    s.sendall(pickle.dumps(mensaje))
            except Exception as e:
                print(f"Error al distribuir inventario a sucursal {id_suc}: {e}")

    def iniciar(self):
        threading.Thread(target=self.servidor, daemon=True).start()
        print("Nodo Maestro iniciado.")
        while True:
            self.distribuir_inventario()
            time.sleep(60)  # Distribuye cada 60 seg (ejemplo)

class NodoSucursal:
    def __init__(self, id_sucursal, puerto, ip_maestro, puerto_maestro, nodos_otras_sucursales):
        self.id = id_sucursal
        self.puerto = puerto
        self.ip_maestro = ip_maestro
        self.puerto_maestro = puerto_maestro
        self.nodos_otras_sucursales = nodos_otras_sucursales
        self.inventario = {}
        self.clientes = {}  # {cliente_id: datos}
        self.lock = threading.Lock()

    def servidor(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.puerto))
            s.listen()
            print(f"Sucursal {self.id} escuchando en puerto {self.puerto}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.manejar_conexion, args=(conn,)).start()

    def manejar_conexion(self, conn):
        with conn:
            data = b''
            while True:
                parte = conn.recv(4096)
                if not parte:
                    break
                data += parte
            if not data:
                return
            mensaje = pickle.loads(data)
            tipo = mensaje.get('tipo')
            respuesta = {}

            if tipo == 'actualizar_inventario':
                # Recibe actualización de maestro
                inventario_nuevo = mensaje.get('inventario')
                with self.lock:
                    self.inventario = inventario_nuevo
                respuesta = {'tipo': 'inventario_actualizado'}

            elif tipo == 'consulta_cliente':
                cliente_id = mensaje.get('cliente_id')
                with self.lock:
                    datos = self.clientes.get(cliente_id)
                respuesta = {'tipo': 'respuesta_cliente', 'datos': datos}

            elif tipo == 'actualizar_cliente':
                cliente_id = mensaje.get('cliente_id')
                datos = mensaje.get('datos')
                with self.lock:
                    self.clientes[cliente_id] = datos
                # Notificar a otras sucursales
                threading.Thread(target=self.propagar_cliente, args=(cliente_id, datos)).start()
                respuesta = {'tipo': 'cliente_actualizado'}

            elif tipo == 'comprar_articulo':
                articulo = mensaje.get('articulo_id')
                cantidad = mensaje.get('cantidad')
                exito = self.comprar(articulo, cantidad)
                respuesta = {'tipo': 'respuesta_compra', 'exito': exito}

            conn.sendall(pickle.dumps(respuesta))

    def propagar_cliente(self, cliente_id, datos):
        for id_suc, (ip, puerto) in self.nodos_otras_sucursales.items():
            if id_suc == self.id:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, puerto))
                    mensaje = {
                        'tipo': 'actualizar_cliente',
                        'cliente_id': cliente_id,
                        'datos': datos
                    }
                    s.sendall(pickle.dumps(mensaje))
            except:
                print(f"Error propagando cliente a sucursal {id_suc}")

    def comprar(self, articulo_id, cantidad):
        # Paso 1: pedir lock al maestro
        if not self.pedir_lock(articulo_id):
            print(f"Compra falló: articulo {articulo_id} bloqueado")
            return False

        # Paso 2: verificar inventario local
        with self.lock:
            stock = self.inventario.get(articulo_id, 0)
            if stock < cantidad:
                print(f"Compra falló: no hay stock suficiente de {articulo_id}")
                self.liberar_lock(articulo_id)
                return False

            # Actualizar inventario local
            self.inventario[articulo_id] -= cantidad

        # Paso 3: notificar venta al maestro para actualizar inventario global
        self.notificar_venta(articulo_id, cantidad)

        # Paso 4: liberar lock
        self.liberar_lock(articulo_id)

        print(f"Compra exitosa de {cantidad} unidades de {articulo_id}")
        return True

    def pedir_lock(self, articulo_id):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip_maestro, self.puerto_maestro))
                mensaje = {
                    'tipo': 'bloquear_articulo',
                    'articulo_id': articulo_id,
                    'origen': self.id
                }
                s.sendall(pickle.dumps(mensaje))
                data = s.recv(4096)
                respuesta = pickle.loads(data)
                return respuesta.get('tipo') == 'lock_confirmado'
        except:
            return False

    def liberar_lock(self, articulo_id):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip_maestro, self.puerto_maestro))
                mensaje = {
                    'tipo': 'liberar_articulo',
                    'articulo_id': articulo_id,
                    'origen': self.id
                }
                s.sendall(pickle.dumps(mensaje))
                s.recv(4096)  # Ignorar respuesta
        except:
            pass

    def notificar_venta(self, articulo_id, cantidad):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip_maestro, self.puerto_maestro))
                mensaje = {
                    'tipo': 'actualizar_inventario',
                    'articulo_id': articulo_id,
                    'cantidad': cantidad
                }
                s.sendall(pickle.dumps(mensaje))
                s.recv(4096)  # Ignorar respuesta
        except:
            pass

    def iniciar(self):
        threading.Thread(target=self.servidor, daemon=True).start()
        print(f"Sucursal {self.id} iniciada")
        # Al iniciar, consultar inventario maestro
        self.consultar_inventario_maestro()

    def consultar_inventario_maestro(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.ip_maestro, self.puerto_maestro))
                mensaje = {'tipo': 'solicitar_inventario'}
                s.sendall(pickle.dumps(mensaje))
                data = s.recv(4096)
                respuesta = pickle.loads(data)
                if respuesta.get('tipo') == 'inventario':
                    with self.lock:
                        self.inventario = respuesta['inventario']
                    print(f"Sucursal {self.id} actualizó inventario desde maestro")
        except Exception as e:
            print(f"Error consultando inventario maestro: {e}")

# Ejemplo de ejecución

if __name__ == "__main__":
    # Configuración nodos
    NODOS_SUCURSALES = {
        2: ('127.0.0.1', 6002),
        3: ('127.0.0.1', 6003),
    }

    # Iniciar maestro en hilo aparte
    maestro = NodoMaestro(puerto=6000, nodos_sucursales=NODOS_SUCURSALES)
    threading.Thread(target=maestro.iniciar, daemon=True).start()

    # Iniciar sucursales
    sucursal2 = NodoSucursal(2, 6002, '127.0.0.1', 6000, NODOS_SUCURSALES)
    sucursal3 = NodoSucursal(3, 6003, '127.0.0.1', 6000, NODOS_SUCURSALES)
    sucursal2.iniciar()
    sucursal3.iniciar()

    # Demo compra en sucursal 2
    time.sleep(2)
    exito = sucursal2.comprar('A001', 5)
    print("Compra sucursal 2:", "Exitosa" if exito else "Fallida")

    # Demo actualización clientes
    cliente_demo = {'nombre': 'Juan Pérez', 'email': 'juan@example.com'}
    sucursal2.manejar_conexion = lambda conn=None: None  # deshabilitar servidor para demo
    sucursal2.propagar_cliente('cliente1', cliente_demo)

    time.sleep(5)
