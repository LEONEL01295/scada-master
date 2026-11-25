import socket
import json
import time

# Variable global para mantener la conexión y paros de emergencia
conexion_cliente = None
paro_emergencia_activado = False

def comprobar_paro_emergencia():
    """Comprueba si se envió una orden de paro de emergencia"""
    global paro_emergencia_activado
    if paro_emergencia_activado:
        paro_emergencia_activado = False
        return True
    return False

def sleep_paso(segundos, servidor=None, callback=None):
    """Pausa no bloqueante que atiende el socket TCP durante la espera para no perder conexión con la App"""
    inicio = time.ticks_ms()
    ms = int(segundos * 1000)
    while time.ticks_diff(time.ticks_ms(), inicio) < ms:
        if servidor and callback:
            atender_conexiones(servidor, callback)
        time.sleep(0.01)

def recibir_mensaje(conn):
    """
    Lee mensajes directos (Socket RAW) de Flutter.
    """
    try:
        datos = conn.recv(1024)
        if not datos:
            return None
        return datos.decode('utf-8').strip()
    except OSError:
        return ""
    except Exception as e:
        return None

def enviar_mensaje(conn, mensaje):
    """
    Envía mensaje directo de texto a Flutter.
    """
    try:
        conn.send((mensaje + "\n").encode('utf-8'))
    except Exception as e:
        pass

def iniciar_servidor(puerto=8080):
    """
    Inicia servidor TCP RAW (máxima estabilidad para MicroPython).
    """
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(('0.0.0.0', puerto))
    servidor.listen(1)
    servidor.setblocking(False)
    print(f"Servidor RAW activo en puerto {puerto}... [ESTABILIDAD MEJORADA]")
    return servidor

def atender_conexiones(servidor, procesar_mensaje_callback):
    """
    Gestiona la conexión única sin bloquear el sistema y respondiendo pings de Flutter.
    """
    global conexion_cliente, paro_emergencia_activado

    if conexion_cliente is None:
        try:
            conn, addr = servidor.accept()
            print("¡App vinculada desde:", addr, "!")
            conn.settimeout(0.01)
            conexion_cliente = conn
        except OSError:
            pass
    else:
        try:
            mensaje_recibido = recibir_mensaje(conexion_cliente)

            if mensaje_recibido is None:
                raise Exception("Enlace perdido")

            if mensaje_recibido != "":
                # Responder pings inmediatamente para mantener el canal vivo
                if '"comando": "ping"' in mensaje_recibido or '"ping"' in mensaje_recibido:
                    enviar_mensaje(conexion_cliente, json.dumps({"comando": "pong"}))
                    return

                if 'emergency_stop' in mensaje_recibido or 'reset' in mensaje_recibido:
                    paro_emergencia_activado = True

                print("App manda:", mensaje_recibido)
                respuesta = procesar_mensaje_callback(mensaje_recibido)
                if respuesta:
                    enviar_mensaje(conexion_cliente, respuesta)

        except Exception:
            try:
                conexion_cliente.close()
            except:
                pass
            conexion_cliente = None
