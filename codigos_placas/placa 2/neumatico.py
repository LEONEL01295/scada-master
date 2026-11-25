from machine import Pin, I2C
import time
import servidor_app

# I2C compartido
i2c = I2C(0, scl=Pin(5), sda=Pin(4))

# Direcciones I2C (Placa 2)
DIRECCION_ENTRADAS = 0x22
DIRECCION_RELES    = 0x25

# Estado interno de relés (0xFF = Todos Apagados)
estado_reles_neumatico = 0xFF

# Máscaras Sensores Neumático (Originales)
btm_est1  = 0b00000101
btm_est2  = 0b00001110
btm_est3  = 0b00001100
btm_est4  = 0b00100100

def apagar_todo():
    """Apaga actuadores de neumático (0b11111111)"""
    global estado_reles_neumatico
    estado_reles_neumatico = 0xFF
    try: i2c.writeto(DIRECCION_RELES, bytes([0xFF]))
    except Exception as e: print("Error I2C Neumático apagar:", e)

def controlar_actuador(rele_index, encender):
    """Control manual para Neumático manteniendo estado en memoria"""
    global estado_reles_neumatico
    try:
        if encender:
            estado_reles_neumatico &= ~(1 << rele_index)
        else:
            estado_reles_neumatico |= (1 << rele_index)
        i2c.writeto(DIRECCION_RELES, bytes([estado_reles_neumatico]))
        print(f"Neumático Relé {rele_index} -> {encender} (Hex: {hex(estado_reles_neumatico)})")
    except Exception as e: print("Error I2C Neumático manual:", e)

def ejecutar_ciclo(piezas):
    """Secuencia PROTEGIDA de Neumático - Garantiza el paro de la mesa giratoria"""
    print(f"--- INICIANDO NEUMÁTICO: {piezas} piezas ---")

    for p in range(piezas):
        if servidor_app.comprobar_paro_emergencia(): apagar_todo(); return
        print(f"Procesando pieza {p+1} de {piezas}")

        # FASE 0: Alineación de plataforma con timeout de seguridad (2.5s max)
        alineado = False
        tiempo_inicio = time.ticks_ms()
        print("Alineando plataforma / mesa giratoria...")
        while not alineado:
            if servidor_app.comprobar_paro_emergencia(): apagar_todo(); return
            try:
                in0 = i2c.readfrom(DIRECCION_ENTRADAS, 1)[0]
                if in0 == 173 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2500:
                    print("Plataforma detectada en posición.")
                    apagar_todo() # APAGAR MESA GIRATORIA OBLIGATORIAMENTE
                    time.sleep(1)
                    alineado = True
                else:
                    i2c.writeto(DIRECCION_RELES, bytes([0b10111111])) # Mueve mesa
                time.sleep(0.1)
            except OSError: time.sleep(0.5)

        # INICIO DE SECUENCIA DE ESTADOS (1 al 4)
        estado = 1
        tiempo_estado = time.ticks_ms()

        while estado <= 4:
            if servidor_app.comprobar_paro_emergencia(): apagar_todo(); return
            try:
                # ESTADO 1: Compresor + Pistón empuje + Giro
                if estado == 1:
                    print("Paso 1: Encendiendo compresor")
                    i2c.writeto(DIRECCION_RELES, bytes([0b11111110]))
                    time.sleep(2.5)
                    apagar_todo(); time.sleep(0.5)

                    print("Paso 2: Pistón empuje sale")
                    i2c.writeto(DIRECCION_RELES, bytes([0b11111101]))
                    time.sleep(1.0)

                    print("Paso 3: Pistón empuje retrae")
                    i2c.writeto(DIRECCION_RELES, bytes([0b11111011]))
                    time.sleep(1.0)

                    print("Paso 4: Girando plataforma")
                    i2c.writeto(DIRECCION_RELES, bytes([0b10111111]))
                    time.sleep(1.5)
                    apagar_todo(); time.sleep(0.5)
                    estado = 2
                    tiempo_estado = time.ticks_ms()

                # ESTADO 2: Sensor de empaque y pistón empaquetar
                elif estado == 2:
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS, 1)[0]
                    if (in0 & btm_est2) == 6 or time.ticks_diff(time.ticks_ms(), tiempo_estado) >= 3000:
                        print("Apagando plataforma y activando empaque.")
                        apagar_todo(); time.sleep(0.5)

                        print("Pistón empaquetar sale")
                        i2c.writeto(DIRECCION_RELES, bytes([0b11110111]))
                        time.sleep(1.0)

                        print("Pistón empaquetar retrae")
                        apagar_todo(); time.sleep(0.5)

                        print("Giro + Compresor")
                        i2c.writeto(DIRECCION_RELES, bytes([0b10111110]))
                        time.sleep(2.0)
                        apagar_todo(); time.sleep(0.5)
                        estado = 3
                        tiempo_estado = time.ticks_ms()

                # ESTADO 3: Posición correcta y expulsión
                elif estado == 3:
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS, 1)[0]
                    if (in0 & btm_est3) == 12 or time.ticks_diff(time.ticks_ms(), tiempo_estado) >= 3000:
                        apagar_todo(); time.sleep(0.5)

                        print("Expulsando paquete")
                        i2c.writeto(DIRECCION_RELES, bytes([0b11101111]))
                        time.sleep(1.0)

                        print("Retrayendo expulsión")
                        i2c.writeto(DIRECCION_RELES, bytes([0b11011111]))
                        time.sleep(1.0)

                        print("Banda transportadora ON")
                        i2c.writeto(DIRECCION_RELES, bytes([0b01111111]))
                        time.sleep(2.5)
                        apagar_todo(); time.sleep(0.5)
                        estado = 4
                        tiempo_estado = time.ticks_ms()

                # ESTADO 4: Final de cinta
                elif estado == 4:
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS, 1)[0]
                    if (in0 & btm_est4) == 4 or time.ticks_diff(time.ticks_ms(), tiempo_estado) >= 2000:
                        print("Pieza lista en final. Apagando todo.")
                        apagar_todo(); time.sleep(1)
                        estado = 5 # Termina bucle de pieza

                time.sleep(0.01)
            except OSError: pass

    # APAGADO FINAL DE SEGURIDAD PARA MESA GIRATORIA Y TODOS LOS RELÉS
    apagar_todo()
    print("--- CICLO NEUMÁTICO FINALIZADO ---")
