### Codigo en python

import socket
import threading
import datetime
import time
import pickle
from concurrent.futures import ThreadPoolExecutor
import random

class Nodo:
    def __init__(self, id_nodo, puerto, nodos_conocidos):
        self.id_nodo = id_nodo
        self.puerto = puerto
        self.nodos_conocidos = nodos_conocidos  # Diccionario {id_nodo: (ip, puerto)}
        self.buzon_entrada = []
        self.buzon_salida = []
        self.lock = threading.Lock()
        self.activo = True
        
    def guardar_mensaje(self, mensaje, es_recepcion):
        """Almacena un mensaje en el buzón correspondiente"""
        with self.lock:
            if es_recepcion:
                self.buzon_entrada.append(mensaje)
            else:
                self.buzon_salida.append(mensaje)
            # Guardar en archivo para persistencia
            with open(f"nodo_{self.id_nodo}_mensajes.txt", "a") as f:
                tipo = "RECIBIDO" if es_recepcion else "ENVIADO"
                f.write(f"{tipo} - {mensaje['timestamp']} - De {mensaje['origen']} a {mensaje['destino']}: {mensaje['contenido']}\n")

    def servidor(self):
        """Escucha conexiones entrantes y recibe mensajes"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', self.puerto))
            s.listen()
            print(f"Nodo {self.id_nodo} escuchando en puerto {self.puerto}")
            
            while self.activo:
                try:
                    conn, addr = s.accept()
                    with conn:
                        data = conn.recv(4096)
                        if data:
                            mensaje = pickle.loads(data)
                            self.guardar_mensaje(mensaje, es_recepcion=True)
                            print(f"Nodo {self.id_nodo} recibió mensaje de {mensaje['origen']}: {mensaje['contenido']}")
                            
                            # Enviar confirmación de recepción
                            respuesta = {
                                'origen': self.id_nodo,
                                'destino': mensaje['origen'],
                                'contenido': f"Confirmación de recepción para mensaje: {mensaje['contenido']}",
                                'timestamp': datetime.datetime.now().isoformat()
                            }
                            conn.sendall(pickle.dumps(respuesta))
                except Exception as e:
                    print(f"Error en servidor nodo {self.id_nodo}: {e}")
    
    def enviar_mensaje(self, destino_id, contenido):
        """Envía un mensaje a otro nodo"""
        if destino_id not in self.nodos_conocidos:
            print(f"Error: Nodo {destino_id} desconocido")
            return False
        
        ip, puerto = self.nodos_conocidos[destino_id]
        mensaje = {
            'origen': self.id_nodo,
            'destino': destino_id,
            'contenido': contenido,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, puerto))
                s.sendall(pickle.dumps(mensaje))
                self.guardar_mensaje(mensaje, es_recepcion=False)
                
                # Esperar confirmación
                data = s.recv(4096)
                if data:
                    respuesta = pickle.loads(data)
                    self.guardar_mensaje(respuesta, es_recepcion=True)
                    print(f"Nodo {self.id_nodo} recibió confirmación de {destino_id}: {respuesta['contenido']}")
                    return True
        except Exception as e:
            print(f"Error al enviar mensaje desde nodo {self.id_nodo} a {destino_id}: {e}")
            return False
    
    def interfaz_usuario(self):
        """Interfaz para que el usuario envíe mensajes"""
        while self.activo:
            print("\n--- Menú ---")
            print("Nodos disponibles:", ", ".join(str(id) for id in self.nodos_conocidos if id != self.id_nodo))
            destino = input("Ingrese ID del nodo destino (o 'q' para salir): ")
            if destino.lower() == 'q':
                self.activo = False
                break
            
            try:
                destino_id = int(destino)
                if destino_id == self.id_nodo:
                    print("No puedes enviarte mensajes a ti mismo")
                    continue
                if destino_id not in self.nodos_conocidos:
                    print("ID de nodo inválido")
                    continue
                
                contenido = input("Ingrese el mensaje: ")
                if contenido:
                    # Usar ThreadPoolExecutor para no bloquear la interfaz
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        executor.submit(self.enviar_mensaje, destino_id, contenido)
            except ValueError:
                print("ID debe ser un número")

def iniciar_nodo(config):
    """Inicia un nodo con la configuración dada"""
    nodo = Nodo(config['id'], config['puerto'], config['nodos_conocidos'])
    
    # Iniciar servidor en segundo plano
    threading.Thread(target=nodo.servidor, daemon=True).start()
    
    # Pequeña pausa para asegurar que el servidor esté listo
    time.sleep(1)
    
    # Iniciar interfaz de usuario
    nodo.interfaz_usuario()

if __name__ == "__main__":
    # Configuración de los 8 nodos (debería ser única para cada máquina/nodo)
    # Este diccionario debería ser compartido entre todos los nodos
    TODOS_NODOS = {
        1: ('192.168.1.1', 5001),
        2: ('192.168.1.1', 5002),
        3: ('192.168.1.2', 5003),
        4: ('192.168.1.2', 5004),
        5: ('192.168.1.3', 5005),
        6: ('192.168.1.3', 5006),
        7: ('192.168.1.4', 5007),
        8: ('192.168.1.4', 5008)
    }
    
    # Cada nodo debe tener su propia configuración
    # En la práctica, esto debería estar en archivos de configuración separados
    # o pasarse como argumentos al script
    
    print("Seleccione el número de nodo a iniciar (1-8):")
    id_nodo = int(input())
    
    if id_nodo not in TODOS_NODOS:
        print("ID de nodo inválido")
        exit(1)
    
    # Configuración para este nodo específico
    config = {
        'id': id_nodo,
        'puerto': TODOS_NODOS[id_nodo][1],
        'nodos_conocidos': TODOS_NODOS
    }
    
    iniciar_nodo(config)