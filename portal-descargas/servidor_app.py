import socket
import json
import time

# Variables globales para mantener conexión, buffer y paros de emergencia
conexion_cliente = None
paro_emergencia_activado = False
buffer_recepcion = ""

def comprobar_paro_emergencia():
    """Comprueba si se envió una orden de paro de emergencia"""
    global paro_emergencia_activado
    if paro_emergencia_activado:
        paro_emergencia_activado = False
        return True
    return False

def sleep_paso(segundos, servidor=None, callback=None):
    """Pausa no bloqueante que atiende el socket TCP durante la espera para mantener viva la conexión"""
    inicio = time.ticks_ms()
    ms = int(segundos * 1000)
    while time.ticks_diff(time.ticks_ms(), inicio) < ms:
        if servidor and callback:
            atender_conexiones(servidor, callback)
        time.sleep(0.01)

def iniciar_servidor(puerto=8080):
    """
    Inicia servidor TCP RAW con bufferizado por líneas para máxima estabilidad en MicroPython.
    """
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(('0.0.0.0', puerto))
    servidor.listen(1)
    servidor.setblocking(False)
    print(f"Servidor RAW activo en puerto {puerto}... [ESTABILIDAD TOTAL]")
    return servidor

def atender_conexiones(servidor, procesar_mensaje_callback):
    """
    Procesa mensajes TCP acumulados en buffer procesando línea por línea.
    """
    global conexion_cliente, paro_emergencia_activado, buffer_recepcion

    if conexion_cliente is None:
        try:
            conn, addr = servidor.accept()
            print("¡App vinculada desde:", addr, "!")
            conn.settimeout(0.01)
            conexion_cliente = conn
            buffer_recepcion = ""
        except OSError:
            pass
    else:
        try:
            raw = conexion_cliente.recv(1024)
            if not raw:
                raise Exception("Enlace cerrado por cliente")

            buffer_recepcion += raw.decode('utf-8', 'ignore')

            while '\n' in buffer_recepcion:
                pos = buffer_recepcion.find('\n')
                linea = buffer_recepcion[:pos].strip()
                buffer_recepcion = buffer_recepcion[pos + 1:]

                if not linea:
                    continue

                if '"ping"' in linea or 'ping' in linea:
                    try:
                        conexion_cliente.send((json.dumps({"comando": "pong"}) + "\n").encode('utf-8'))
                    except: pass
                    continue

                if 'emergency_stop' in linea or 'reset' in linea:
                    paro_emergencia_activado = True

                print("App manda:", linea)
                resp = procesar_mensaje_callback(linea)
                if resp:
                    try:
                        conexion_cliente.send((resp + "\n").encode('utf-8'))
                    except: pass

        except OSError:
            pass
        except Exception as e:
            print("Reiniciando canal por:", e)
            try:
                conexion_cliente.close()
            except: pass
            conexion_cliente = None
            buffer_recepcion = ""
