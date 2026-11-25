from machine import Pin, I2C
import time
import servidor_app

# I2C compartido
i2c = I2C(0, scl=Pin(5), sda=Pin(4))

# Direcciones I2C (Placa 2)
DIRECCION_ENTRADAS_P2 = 0x22
DIRECCION_ENTRADAS_P1 = 0x21 # Sensores imanes
DIRECCION_RELES       = 0x24

# Estado interno de relés (0xFF = Todos Apagados)
estado_reles_maquinados = 0xFF

# Máscaras Maquinados (Originales)
btm_est5  = 0b10000100
btm_est6  = 0b00000001
btm_est7  = 0b00000010
btm_est8  = 0b00000100
btm_est9  = 0b00010000
btm_est10 = 0b00100000

def apagar_todo():
    """Apaga actuadores de maquinados (0b11111111)"""
    global estado_reles_maquinados
    estado_reles_maquinados = 0xFF
    try: i2c.writeto(DIRECCION_RELES, bytes([0xFF]))
    except Exception as e: print("Error I2C Maquinados apagar:", e)

def controlar_actuador(rele_index, encender):
    """Control manual para Maquinados manteniendo estado en memoria"""
    global estado_reles_maquinados
    try:
        if encender:
            estado_reles_maquinados &= ~(1 << rele_index)
        else:
            estado_reles_maquinados |= (1 << rele_index)
        i2c.writeto(DIRECCION_RELES, bytes([estado_reles_maquinados]))
        print(f"Maquinados Relé {rele_index} -> {encender} (Hex: {hex(estado_reles_maquinados)})")
    except Exception as e: print("Error I2C Maquinados manual:", e)

def ejecutar_ciclo(piezas):
    """Secuencia PROTEGIDA Y FIABLE de Maquinados con Tiempos de Seguridad"""
    print(f"--- INICIANDO MAQUETA DE MAQUINADOS: {piezas} piezas ---")

    for p in range(piezas):
        if servidor_app.comprobar_paro_emergencia(): apagar_todo(); return
        print(f"Procesando pieza {p+1} de {piezas}")
        estado = 5
        tiempo_inicio = time.ticks_ms()

        # Apagado inicial de seguridad por pieza
        apagar_todo()

        # Bucle de la secuencia original (est5 a est10)
        while estado <= 10:
            if servidor_app.comprobar_paro_emergencia(): apagar_todo(); return
            try:
                # ESTADO 5: Esperando entrada de pieza
                if estado == 5:
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS_P2, 1)[0]
                    entr5 = in0 & btm_est5
                    if entr5 == 4 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2500:
                        time.sleep(1)
                        i2c.writeto(DIRECCION_RELES, bytes([0b11111101])) # Tornillo 1
                        i2c.readfrom(DIRECCION_ENTRADAS_P1, 1)[0]
                        estado = 6
                        tiempo_inicio = time.ticks_ms()

                # ESTADO 6: Imán 1
                elif estado == 6:
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS_P1, 1)[0]
                    entr6 = in0 & btm_est6
                    if entr6 == 0 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        i2c.writeto(DIRECCION_RELES, bytes([0b11111011])) # Tornillo 2
                        estado = 7
                        tiempo_inicio = time.ticks_ms()

                # ESTADO 7: Primer Tornillo / Proceso de Maquinado
                elif estado == 7:
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS_P1, 1)[0]
                    entr7 = in0 & btm_est7
                    if entr7 == 0 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        i2c.writeto(DIRECCION_RELES, bytes([0b11110111]))
                        time.sleep(1)
                        i2c.writeto(DIRECCION_RELES, bytes([0b11101011]))
                        time.sleep(1)
                        i2c.writeto(DIRECCION_RELES, bytes([0b11101011]))
                        time.sleep(0.5)
                        i2c.writeto(DIRECCION_RELES, bytes([0b11101111]))
                        time.sleep(0.5)
                        estado = 8
                        tiempo_inicio = time.ticks_ms()

                # ESTADO 8: Segundo Tornillo por tiempo
                elif estado == 8:
                    i2c.readfrom(DIRECCION_ENTRADAS_P1, 1)[0]
                    i2c.writeto(DIRECCION_RELES, bytes([0b11011111]))
                    time.sleep(1)
                    i2c.writeto(DIRECCION_RELES, bytes([0b11101111]))
                    time.sleep(2)

                    i2c.writeto(DIRECCION_RELES, bytes([0b11111111]))
                    time.sleep(1)
                    i2c.writeto(DIRECCION_RELES, bytes([0b10111111]))
                    estado = 9
                    tiempo_inicio = time.ticks_ms()

                # ESTADO 9: Sensor Est10 / Imán Salida
                elif estado == 9:
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS_P1, 1)[0]
                    entr9 = in0 & btm_est9
                    if entr9 == 0 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        i2c.writeto(DIRECCION_RELES, bytes([0b01111111])) # Banda Final
                        time.sleep(2)
                        estado = 10
                        tiempo_inicio = time.ticks_ms()

                # ESTADO 10: ÚLTIMO TORNILLO / FINALIZACIÓN DE PIEZA
                elif estado == 10:
                    i2c.readfrom(DIRECCION_ENTRADAS_P1, 1)[0]
                    time.sleep(2)
                    apagar_todo()
                    print(f"Pieza {p+1} terminada.")
                    estado = 11

                time.sleep(0.01)
            except OSError:
                time.sleep(0.1)
                pass

    apagar_todo()
    print("--- CICLO DE MAQUINADOS FINALIZADO ---")
