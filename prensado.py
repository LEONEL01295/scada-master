from machine import Pin, I2C
import time
import servidor_app

# I2C compartido
i2c = I2C(0, scl=Pin(5), sda=Pin(4))

# Direcciones I2C (Placa 1)
DIRECCION_ENTRADAS = 0x22
DIRECCION_RELES    = 0x25

# Estado interno de relés (0xFF = Todos Apagados)
estado_reles_prensa = 0xFF

# Máscaras Originales
btm_est1 = 0b00000011  # P1 y S1
btm_est2 = 0b00000001  # P2 y S1
btm_est3 = 0b00001011  # P2 y S2
btm_est4 = 0b00000111  # P2 y S1
MASCARA_ORIGEN = 0b00000100

def apagar_todo():
    """Apaga relés de prensa/banda"""
    global estado_reles_prensa
    estado_reles_prensa = 0xFF
    try: i2c.writeto(DIRECCION_RELES, bytes([0xFF]))
    except Exception as e: print("Error I2C Prensa apagar:", e)

def controlar_actuador(rele_index, encender):
    """Control manual de relés para Prensado/Banda manteniendo estado en memoria"""
    global estado_reles_prensa
    try:
        if encender:
            estado_reles_prensa &= ~(1 << rele_index)
        else:
            estado_reles_prensa |= (1 << rele_index)
        i2c.writeto(DIRECCION_RELES, bytes([estado_reles_prensa]))
        print(f"Prensa Relé {rele_index} -> {encender} (Hex: {hex(estado_reles_prensa)})")
    except Exception as e: print("Error I2C Prensa manual:", e)

def ejecutar_ciclo(piezas):
    """Secuencia PROTEGIDA Y FIABLE de Prensado"""
    print(f"--- PRENSADO: {piezas} piezas ---")

    for p in range(piezas):
        if servidor_app.comprobar_paro_emergencia(): apagar_todo(); return
        print(f"Procesando pieza {p+1}/{piezas}")
        estado = 14 # EST_PRENSA_ALINEAR
        motor_inicializado = False
        tiempo_inicio = time.ticks_ms()

        while estado != 24: # EST_FIN_DEFINITIVO
            if servidor_app.comprobar_paro_emergencia(): apagar_todo(); return
            try:
                # 14: ALINEACIÓN (S1 ARRIBA)
                if estado == 14:
                    if not motor_inicializado:
                        tiempo_inicio = time.ticks_ms()
                        motor_inicializado = True
                    in0 = i2c.readfrom(DIRECCION_ENTRADAS, 1)[0]
                    if (in0 & MASCARA_ORIGEN) == 4 or time.ticks_diff(time.ticks_ms(), tiempo_inicio) >= 2000:
                        print("Prensa alineada.")
                        apagar_todo(); time.sleep(0.5)
                        estado = 15
                        motor_inicializado = False
                    else:
                        i2c.writeto(DIRECCION_RELES, bytes([0b10111111])) # Sube
                        time.sleep(0.1)

                # 15: BANDA ADELANTE
                elif estado == 15:
                    print("Banda adelante...")
                    i2c.writeto(DIRECCION_RELES, bytes([0b11011111])) # Adelante
                    time.sleep(3.0)
                    apagar_todo(); time.sleep(0.5)
                    estado = 16
                    motor_inicializado = False

                # 16: BAJAR PRENSA (PRENSADO)
                elif estado == 16:
                    print("Bajando prensa...")
                    i2c.writeto(DIRECCION_RELES, bytes([0b01111111])) # Baja
                    time.sleep(1.8) # Prensado por tiempo exacto
                    apagar_todo(); time.sleep(0.5)
                    estado = 17
                    motor_inicializado = False

                # 17: SUBIR PRENSA (LIBERAR)
                elif estado == 17:
                    print("Subiendo prensa...")
                    i2c.writeto(DIRECCION_RELES, bytes([0b10111111])) # Sube
                    time.sleep(1.8) # Subida garantizada
                    apagar_todo(); time.sleep(0.5)
                    estado = 18
                    motor_inicializado = False

                # 18: REVERSA BANDA
                elif estado == 18:
                    print("Reversa banda...")
                    i2c.writeto(DIRECCION_RELES, bytes([0b11101111])) # Reversa
                    time.sleep(3.0)
                    apagar_todo(); time.sleep(0.5)
                    estado = 24

                time.sleep(0.005)
            except OSError: pass

    print("--- CICLO PRENSADO FINALIZADO ---")
