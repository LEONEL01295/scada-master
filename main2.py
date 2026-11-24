from machine import Pin, I2C
import time
import json
import servidor_app

# Inicializar I2C global (Placa 2)
i2c = I2C(0, scl=Pin(5), sda=Pin(4))

# Máscaras Originales Unificadas
btm_est1  = 0b00000101
btm_est2  = 0b00001110
btm_est3  = 0b00001100
btm_est4  = 0b00100100
btm_est5  = 0b10000100
btm_est6  = 0b00000001
btm_est7  = 0b00000010
btm_est8  = 0b00000100
btm_est9  = 0b00010000
btm_est10 = 0b00100000

def apagar_emergencia():
    """Apaga actuadores de ambas maquetas en Placa 2 (0b11111111)"""
    try:
        i2c.writeto(0x25, bytes([0b11111111])) # Neumático
        i2c.writeto(0x24, bytes([0b11111111])) # Maquinados
        print(">>> PLACA 2 DESENERGIZADA <<<")
    except: pass

def ejecutar_ciclo_unificado_p2(piezas):
    """Ejecuta la lógica unificada de P2 (Neumático -> Maquinados) de forma protegida"""
    print(f"--- INICIANDO SISTEMA INTEGRADO PLACA 2: {piezas} piezas ---")

    for p in range(piezas):
        if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return
        print(f"Procesando pieza {p+1}/{piezas}")
        estado = 1
        a = 0
        tiempo_inicio = time.ticks_ms()

        while estado <= 10:
            if servidor_app.comprobar_paro_emergencia(): apagar_emergencia(); return
            try:
                # FASE ALINEACIÓN MESA GIRATORIA (Con timeout de seguridad de 2.5s)
                if a != 23:
                    in0 = i2c.readfrom(0x22, 1)[0]
                    if in0 == 173 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2500:
                        a = 23
                        print("Plataforma en posición.")
                        i2c.writeto(0x25, bytes([0b11111111])) # Apagar giro obligatoriamente
                        time.sleep(1)
                    else:
                        i2c.writeto(0x25, bytes([0b10111111]))
                        time.sleep(0.1)
                        continue

                # --- LÓGICA NEUMÁTICA (ESTADOS 1-4) ---
                if estado == 1:
                    in0 = i2c.readfrom(0x22, 1)[0]
                    if (in0 & btm_est1) == 4 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 3000:
                        i2c.writeto(0x25, bytes([0b11111110])); time.sleep(2.5) # Compresor
                        i2c.writeto(0x25, bytes([0b11111111])); time.sleep(0.5)
                        i2c.writeto(0x25, bytes([0b11111101])); time.sleep(1.0) # Piston Sale
                        i2c.writeto(0x25, bytes([0b11111011])); time.sleep(1.0) # Piston Entra
                        i2c.writeto(0x25, bytes([0b10111111])); time.sleep(1.5) # Giro
                        i2c.writeto(0x25, bytes([0b11111111]))
                        estado = 2
                        tiempo_inicio = time.ticks_ms()

                elif estado == 2:
                    in0 = i2c.readfrom(0x22, 1)[0]
                    if (in0 & btm_est2) == 6 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 3000:
                        i2c.writeto(0x25, bytes([0b11111111])); time.sleep(0.5)
                        i2c.writeto(0x25, bytes([0b11110111])); time.sleep(1.0) # Empaque
                        i2c.writeto(0x25, bytes([0b11111111])); time.sleep(0.5)
                        i2c.writeto(0x25, bytes([0b10111110])); time.sleep(2.0) # Giro + Comp
                        i2c.writeto(0x25, bytes([0b11111111]))
                        estado = 3
                        tiempo_inicio = time.ticks_ms()

                elif estado == 3:
                    in0 = i2c.readfrom(0x22, 1)[0]
                    if (in0 & btm_est3) == 12 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 3000:
                        i2c.writeto(0x25, bytes([0b11111111])); time.sleep(0.5)
                        i2c.writeto(0x25, bytes([0b11101111])); time.sleep(1.0) # Expulsion
                        i2c.writeto(0x25, bytes([0b11011111]); time.sleep(1.0)
                        i2c.writeto(0x25, bytes([0b01111111])); time.sleep(2.5) # Banda
                        i2c.writeto(0x25, bytes([0b11111111]))
                        estado = 4
                        tiempo_inicio = time.ticks_ms()

                elif estado == 4:
                    in0 = i2c.readfrom(0x22, 1)[0]
                    if (in0 & btm_est4) == 4 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        i2c.writeto(0x24, bytes([0b11111110])); time.sleep(1.5) # Transición a P2
                        i2c.writeto(0x25, bytes([0b11111111]))
                        estado = 5
                        tiempo_inicio = time.ticks_ms()

                # --- LÓGICA MAQUINADOS (ESTADOS 5-10) ---
                elif estado == 5:
                    in0 = i2c.readfrom(0x22, 1)[0]
                    if (in0 & btm_est5) == 4 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        time.sleep(1)
                        i2c.writeto(0x24, bytes([0b11111101])) # Tornillo 1
                        estado = 6
                        tiempo_inicio = time.ticks_ms()

                elif estado == 6:
                    in0 = i2c.readfrom(0x21, 1)[0]
                    entr6 = in0 & btm_est6
                    if entr6 == 0 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        i2c.writeto(0x24, bytes([0b11111011])) # Tornillo 2
                        estado = 7
                        tiempo_inicio = time.ticks_ms()

                elif estado == 7:
                    in0 = i2c.readfrom(0x21, 1)[0]
                    if (in0 & btm_est7) == 0 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        i2c.writeto(0x24, bytes([0b11110111])); time.sleep(1)
                        i2c.writeto(0x24, bytes([0b11101011])); time.sleep(1)
                        i2c.writeto(0x24, bytes([0b11101111])); time.sleep(0.5)
                        estado = 8
                        tiempo_inicio = time.ticks_ms()

                elif estado == 8:
                    i2c.writeto(0x24, bytes([0b11011111])); time.sleep(1)
                    i2c.writeto(0x24, bytes([0b11101111])); time.sleep(2)
                    i2c.writeto(0x24, bytes([0b11111111])); time.sleep(1)
                    i2c.writeto(0x24, bytes([0b10111111])) # Empujador Final
                    estado = 9
                    tiempo_inicio = time.ticks_ms()

                elif estado == 9:
                    in0 = i2c.readfrom(0x21, 1)[0]
                    entr9 = in0 & btm_est9
                    if entr9 == 0 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        i2c.writeto(0x24, bytes([0b01111111])) # Banda Final
                        time.sleep(2)
                        estado = 10

                elif estado == 10:
                    time.sleep(2)
                    apagar_emergencia()
                    print(f"Pieza {p+1} terminada.")
                    estado = 11

                time.sleep(0.01)
            except OSError:
                time.sleep(0.1)
                pass

    apagar_emergencia()
    print("--- CICLO INTEGRADO P2 FINALIZADO ---")

def procesar_orden(mensaje):
    """Callback para procesar comandos de la App"""
    try:
        data = json.loads(mensaje)
        cmd = data.get("comando")
        maqueta = data.get("maqueta")
        piezas = data.get("piezas", 1)

        if cmd == "start":
            apagar_emergencia()
            time.sleep(0.3)

            # Ejecución según modo del Panel General
            if maqueta == "neumatico":
                import neumatico
                neumatico.ejecutar_ciclo(piezas)
            elif maqueta == "maquinados":
                import maquinados
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

            import neumatico, maquinados
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
