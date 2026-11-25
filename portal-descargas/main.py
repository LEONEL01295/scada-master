from machine import Pin, I2C
import time
import json
import servidor_app
import robot
import prensado

# Inicializar I2C
i2c = I2C(0, scl=Pin(5), sda=Pin(4))

# -------------------------------------------------------------------------
# MÁSCARAS DE SENSADO - BRAZO (DIRECCIÓN I2C: 0x21)
# -------------------------------------------------------------------------
MASK_S1 = 0b00000010  # M1: Pulsos de la base
MASK_S3 = 0b00000100  # M2: Pulsos del brazo
MASK_S4 = 0b00001000  # M2: Tope/Referencia hacia atrás
MASK_S7 = 0b01000000  # M4: Pulsos de la pinza
MASK_S8 = 0b10000000  # M4: Tope/Referencia de pinza abierta

# Globales para sincronización y modos
sync_signal = None
modo_actual = "placa1"

def apagar_emergencia():
    """Apaga todas las tarjetas de relevadores de Placa 1 (0b11111111)"""
    try:
        i2c.writeto(0x24, bytes([0b11111111])) # Apagar brazo
        i2c.writeto(0x25, bytes([0b11111111])) # Apagar prensa y banda
        print(">>> PLACA 1 DESENERGIZADA <<<")
    except: pass

def ejecutar_ciclo_unificado_p1(piezas):
    """
    Secuencia de Producción Placa 1 (Robot + Prensa).
    - Si modo_actual == "general": Espera notificación de Placa 2.
    - Si modo_actual == "placa1": Se ejecuta inmediatamente en solitario.
    """
    global sync_signal, modo_actual
    print(f"--- INICIANDO P1 (Modo: {modo_actual}): {piezas} piezas ---")

    for p in range(piezas):
        if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return

        # Solo esperar a Placa 2 si estamos en ejecución "general"
        if modo_actual == "general":
            print("P1: Esperando señal de finalización de Maquinados (P2)...")
            t_wait = time.ticks_ms()
            while sync_signal != "maquinado_finalizado":
                if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return
                if time.ticks_diff(time.ticks_ms(), t_wait) >= 30000:
                    print("P1: Timeout de red. Continuando secuencia del robot...")
                    break
                time.sleep(0.1)
            sync_signal = None
        else:
            print(f"P1: Modo '{modo_actual}' activo. Ejecutando de forma aislada sin esperar a Placa 2.")

        # =====================================================================
        # PASO 1: ROBOT RECOGE EN MAQUINADOS
        # =====================================================================
        print("P1: Robot bajando sobre Maquinados...")
        i2c.writeto(0x24, bytes([0b11101111])) # M2 atrás
        time.sleep(1.0)
        i2c.writeto(0x24, bytes([0b11011111])) # M2 adelante
        time.sleep(1.2)
        i2c.writeto(0x24, bytes([0b01111111])) # M1 Izquierda hacia Maquinados
        time.sleep(2.0)
        i2c.writeto(0x24, bytes([0b11111011])) # Bajar M3
        time.sleep(2.8)
        i2c.writeto(0x24, bytes([0b11111111])) # Detener

        print("P1: Abriendo pinza M4...")
        i2c.writeto(0x24, bytes([0b11111101])) # Abrir pinza
        time.sleep(1.0)

        print("P1: Esperando pulsación del bit/sensor del paquete...")
        t_inicio = time.ticks_ms()
        while True:
            if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return
            lectura = i2c.readfrom(0x21, 1)[0]
            if (lectura & MASK_S8) != 0 or (lectura & MASK_S7) != 0 or time.ticks_diff(time.ticks_ms(), t_inicio) >= 2500:
                break
            time.sleep(0.01)

        print("P1: Bit presionado. Cerrando pinza M4...")
        i2c.writeto(0x24, bytes([0b11111110])) # Cerrar pinza
        time.sleep(1.2)

        print("P1: Subiendo brazo M3 y trasladando a Prensado...")
        i2c.writeto(0x24, bytes([0b11110111])) # Subir M3
        time.sleep(2.8)
        i2c.writeto(0x24, bytes([0b10111111])) # M1 Derecha hacia Prensa
        time.sleep(1.5)
        i2c.writeto(0x24, bytes([0b11111011])) # Bajar M3 sobre Prensa
        time.sleep(2.8)
        i2c.writeto(0x24, bytes([0b11111101])) # Abrir pinza depositando paquete
        time.sleep(1.0)
        i2c.writeto(0x24, bytes([0b11110111])) # Subir M3 libre
        time.sleep(2.5)
        i2c.writeto(0x24, bytes([0b11111111])) # Detener robot

        if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return

        # =====================================================================
        # PASO 2: PRENSADO AUTOMÁTICO
        # =====================================================================
        print("P1: Iniciando ciclo de Prensado...")
        prensado.ejecutar_ciclo(1)

        if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return

        # =====================================================================
        # PASO 3: ROBOT RECOGE EN PRENSADO Y DEPOSITA EN BASE CONTENEDOR FINAL
        # =====================================================================
        print("P1: Robot bajando por paquete sobre Prensado...")
        i2c.writeto(0x24, bytes([0b11111011])) # Bajar M3
        time.sleep(2.8)

        print("P1: Abriendo pinza M4...")
        i2c.writeto(0x24, bytes([0b11111101])) # Abrir pinza
        time.sleep(1.0)

        print("P1: Esperando pulsación del bit/sensor en Prensado...")
        t_inicio = time.ticks_ms()
        while True:
            if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return
            lectura = i2c.readfrom(0x21, 1)[0]
            if (lectura & MASK_S8) != 0 or (lectura & MASK_S7) != 0 or time.ticks_diff(time.ticks_ms(), t_inicio) >= 2500:
                break
            time.sleep(0.01)

        print("P1: Bit presionado. Cerrando pinza M4...")
        i2c.writeto(0x24, bytes([0b11111110])) # Cerrar pinza
        time.sleep(1.2)

        print("P1: Subiendo brazo, girando a la derecha hacia posición inicial...")
        i2c.writeto(0x24, bytes([0b11110111])) # Subir M3
        time.sleep(2.8)
        i2c.writeto(0x24, bytes([0b10111111])) # M1 Derecha hacia Posición Inicial / Base Final
        time.sleep(2.5)

        print("P1: Bajando brazo y dejando paquete en la base contenedora final...")
        i2c.writeto(0x24, bytes([0b11111011])) # Bajar M3
        time.sleep(2.5)
        i2c.writeto(0x24, bytes([0b11111101])) # Abrir pinza dejando paquete
        time.sleep(1.0)
        i2c.writeto(0x24, bytes([0b11110111])) # Subir M3 a origen
        time.sleep(2.5)
        apagar_emergencia()

        print(f"✔ Pieza {p+1}/{piezas} depositada en Base Final de Acopio.")

    apagar_emergencia()
    print("--- CICLO INTEGRADO P1 FINALIZADO ---")

def procesar_orden(mensaje):
    global sync_signal, modo_actual
    try:
        data = json.loads(mensaje)
        cmd = data.get("comando")
        maqueta = data.get("maqueta")
        piezas = data.get("piezas", 1)

        if cmd == "sync_robot":
            sync_signal = data.get("msg")
            print("P1: Recibida señal de red:", sync_signal)
            return json.dumps({"status": "ok"})

        if cmd == "start":
            modo_actual = maqueta if maqueta else "placa1"
            apagar_emergencia()
            time.sleep(0.3)

            if maqueta == "robot":
                robot.ejecutar_ciclo(piezas)
            elif maqueta == "prensado":
                prensado.ejecutar_ciclo(piezas)
            else: # "placa1" o "general"
                ejecutar_ciclo_unificado_p1(piezas)

            return json.dumps({"status": "ok", "msg": "Ciclo en Placa 1 Terminado"})

        elif cmd == "manual_control" or cmd == "actuador":
            rele = data.get("rele")
            if rele is None: rele = data.get("actuador")
            valor = data.get("valor")
            if valor is None: valor = data.get("estado")
            try: rele = int(rele)
            except: pass

            import robot, prensado
            if maqueta == "robot": robot.controlar_actuador(rele, valor)
            else: prensado.controlar_actuador(rele, valor)
            return json.dumps({"status": "ok"})

        elif cmd == "emergency_stop" or cmd == "reset":
            apagar_emergencia()
            return json.dumps({"status": "ready"})

    except Exception as e:
        print("Error en P1:", e)
        return None

# Asegurar apagado inicial
apagar_emergencia()
time.sleep(0.5)

print("--- CONTROLADOR PLACA 1 ACTIVO ---")
servidor = servidor_app.iniciar_servidor()

while True:
    try:
        servidor_app.atender_conexiones(servidor, procesar_orden)
    except: pass
    time.sleep(0.002)
