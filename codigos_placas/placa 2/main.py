from machine import Pin, I2C
import time
import json
import socket
import servidor_app
import neumatico
import maquinados

# Inicializar I2C global (Placa 2)
i2c = I2C(0, scl=Pin(5), sda=Pin(4))

modo_actual = "placa2"

def apagar_emergencia():
    """Apaga actuadores de ambas maquetas en Placa 2 (0b11111111)"""
    try:
        i2c.writeto(0x25, bytes([0b11111111])) # Neumático
        i2c.writeto(0x24, bytes([0b11111111])) # Maquinados
        print(">>> PLACA 2 DESENERGIZADA <<<")
    except: pass

def notificar_placa1(mensaje):
    """Envía señal de red TCP a Placa 1 para coordinar el Robot 3 Ejes"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(('192.168.4.1', 8080))
        s.send((json.dumps({"comando": "sync_robot", "msg": mensaje}) + '\n').encode('utf-8'))
        s.close()
        print("P2: Notificado exitosamente a Placa 1:", mensaje)
    except Exception as e:
        print("Error notificando a Placa 1:", e)

def ejecutar_ciclo_unificado_p2(piezas):
    """
    Lógica de Producción P2 (Neumático -> Maquinados):
    - Si modo_actual == "general": Notifica a Placa 1 para continuar.
    - Si modo_actual == "placa2": Ejecuta solo P2 en aislamiento total.
    """
    global modo_actual
    print(f"--- INICIANDO P2 (Modo: {modo_actual}): {piezas} piezas ---")

    for p in range(piezas):
        if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return
        print(f"P2: Procesando Neumático pieza {p+1}/{piezas}...")

        # 1. EJECUTAR NEUMÁTICO
        neumatico.ejecutar_ciclo(1)

        if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return
        print(f"P2: Neumático finalizado. Activando Maquinados...")

        # 2. EJECUTAR MAQUINADOS
        maquinados.ejecutar_ciclo(1)

        if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return

        # Notificar a Placa 1 ÚNICAMENTE en modo General
        if modo_actual == "general":
            print(f"P2: Modo 'general' activo. Notificando a Placa 1 (Robot + Prensa)...")
            notificar_placa1("maquinado_finalizado")
            time.sleep(1.0)
        else:
            print(f"P2: Modo '{modo_actual}' activo. Finalizado en aislamiento sin enviar señal a Placa 1.")

    apagar_emergencia()
    print("--- CICLO INTEGRADO P2 FINALIZADO ---")

def procesar_orden(mensaje):
    global modo_actual
    try:
        data = json.loads(mensaje)
        cmd = data.get("comando")
        maqueta = data.get("maqueta")
        piezas = data.get("piezas", 1)

        if cmd == "start":
            modo_actual = maqueta if maqueta else "placa2"
            apagar_emergencia()
            time.sleep(0.3)

            if maqueta == "neumatico":
                neumatico.ejecutar_ciclo(piezas)
            elif maqueta == "maquinados":
                maquinados.ejecutar_ciclo(piezas)
            else: # "placa2" o "general"
                ejecutar_ciclo_unificado_p2(piezas)

            return json.dumps({"status": "ok", "msg": "Ciclo en Placa 2 Terminado"})

        elif cmd == "manual_control" or cmd == "actuador":
            rele = data.get("rele")
            if rele is None: rele = data.get("actuador")
            valor = data.get("valor")
            if valor is None: valor = data.get("estado")
            try: rele = int(rele)
            except: pass

            if maqueta == "neumatico": neumatico.controlar_actuador(rele, valor)
            else: maquinados.controlar_actuador(rele, valor)
            return json.dumps({"status": "ok"})

        elif cmd == "emergency_stop" or cmd == "reset":
            apagar_emergencia()
            return json.dumps({"status": "ready"})

    except Exception as e:
        print("Error en P2:", e)
        return None

# Asegurar apagado inicial
apagar_emergencia()
time.sleep(0.5)

print("--- CONTROLADOR PLACA 2 ACTIVO ---")
servidor = servidor_app.iniciar_servidor()

while True:
    try:
        servidor_app.atender_conexiones(servidor, procesar_orden)
    except: pass
    time.sleep(0.002)
