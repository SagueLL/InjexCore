import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(42)

n = 2000

data = []

start_time = datetime.now()

for i in range(n):

    drift = min(i * 0.002, 5) # Drift con saturación (La máquina se degrada, pero no indefinidamente)
    
    tiempo = start_time + timedelta(seconds=i*40)
    
    # VARIABLES BASE (normales)
    temp_mat = 220 + drift + np.random.normal(0, 3)
    temp_molde = np.random.normal(50, 3)
    
    velocidad = np.random.normal(80, 10)
    
    # RELACIONES FÍSICAS
    presion_iny = 290 - (temp_mat - 220)*2 + np.random.normal(5, 10)
    presion_mant = presion_iny * np.random.uniform(0.6, 0.9)
    presion_cav = presion_iny * np.random.uniform(0.7, 0.9)
    
    tiempo_iny = np.random.normal(3, 0.3)
    tiempo_enf = np.random.normal(27, 2)
    tiempo_ciclo = tiempo_iny + tiempo_enf + np.random.normal(5,1)
    
    posicion = np.random.normal(100, 5)
    
    volumen = 1 / (1 + (presion_cav/1000)) + np.random.normal(0, 0.01)
    
    energia = 0.05 * presion_iny + 0.1 * tiempo_ciclo + np.random.normal(0, 1)
    
    estado = "normal"
    tipo_anomalia = "none"

    anomalia_activa = False
    offset_temp = 0
    offset_presion = 0
    offset_ciclo = 0
    
    # INTRODUCIR ANOMALÍAS
    if not anomalia_activa and np.random.rand() < 0.03:
        
        anomalia_activa = True
        

        # Introducción de distintos tipos de anomalías segun su duración
        tipo_duracion = np.random.choice(["corta", "media", "larga"], p=[0.5, 0.3, 0.2])

        if tipo_duracion == "corta":
            duracion_restante = np.random.randint(3, 8) # Anomalía de corta duración
        elif tipo_duracion == "media":
            duracion_restante = np.random.randint(8,15) # Anomalía de media duración
        else:
            duracion_restante = np.random.randint(15, 30) # Anomalía de larga duración
        

        # Anomalías Temperatura
        offset_temp = np.random.uniform(1, 3)
        temp_max = 240
        temp_min = 210

        # Anomalías Presión
        offset_presion = -np.random.uniform(20, 40)
        presion_max = 350
        presion_min = 150

        # Anomalías ciclo_largo
        offset_ciclo = np.random.uniform(3, 6)
        ciclo_max = 60
        ciclo_min = 25


        # Anomalías multiple

        for j in range(duracion_restante):
            tipo = np.random.choice(["temp_alta", "presion_baja", "ciclo_largo", "multiple"], p=[0.4, 0.3, 0.2, 0.1])


            if anomalia_activa:
                if tipo == "temp_alta":
                    temp_mat = temp_mat + offset_temp
                    temp_mat = np.clip(temp_mat, temp_min, temp_max)
                    drift += 0.2 # Simulación de degradación real
                    duracion_restante -= 1
                    estado = "anomalia"
                    if duracion_restante == 0:
                        anomalia_activa = False
                        offset_temp = 0
                
                elif tipo == "presion_baja":
                    presion_iny = presion_iny + offset_presion
                    presion_iny = np.clip(presion_iny, presion_min, presion_max)
                    presion_iny = max(presion_iny, presion_min + np.random.normal(0, 5))
                    drift += 0.2
                    duracion_restante -= 1
                    estado = "anomalia"
                    if duracion_restante == 0:
                        anomalia_activa = False
                        offset_presion = 0
                
                elif tipo == "ciclo_largo":
                    tiempo_ciclo = tiempo_ciclo + offset_ciclo
                    tiempo_ciclo = np.clip(tiempo_ciclo, ciclo_min, ciclo_max)
                    drift += 0.2
                    duracion_restante -= 1
                    estado = "warning"
                    if duracion_restante == 0:
                        anomalia_activa = False
                        offset_ciclo = 0
                
                elif tipo == "multiple":
                    offset_temp = np.random.randint(1, 2)
                    offset_presion = -np.random.uniform(15, 30)
                    offset_ciclo = np.random.uniform(3, 6)

                    temp_mat = temp_mat + offset_temp
                    temp_mat = np.clip(temp_mat, temp_min, temp_max)

                    presion_iny = presion_iny + offset_presion
                    presion_iny = np.clip(presion_iny, presion_min, presion_max) + offset_presion
                    presion_iny = max(presion_iny, presion_min + np.random.normal(0, 5))

                    tiempo_ciclo = tiempo_ciclo + offset_ciclo
                    tiempo_ciclo = np.clip(tiempo_ciclo, ciclo_min, ciclo_max) + offset_ciclo

                    estado = "anomalia"
                    if duracion_restante == 0:
                        anomalia_activa = False
                        offset_temp = 0
        
            tipo_anomalia = tipo
    
    data.append([
        tiempo, i,
        temp_mat, temp_molde,
        presion_iny, presion_mant, presion_cav,
        velocidad, posicion,
        tiempo_iny, tiempo_enf, tiempo_ciclo,
        volumen, energia,
        estado, tipo_anomalia
    ])

columns = [
    "tiempo", "ciclo_id",
    "temperatura_material", "temperatura_molde",
    "presion_inyeccion", "presion_mantenimiento", "presion_cavidad",
    "velocidad_inyeccion", "posicion_tornillo",
    "tiempo_inyeccion", "tiempo_enfriamiento", "tiempo_ciclo",
    "volumen_especifico", "energia_consumida",
    "estado", "tipo_anomalia"
]

df = pd.DataFrame(data, columns=columns)

df.to_csv("data/raw/dataset_pro.csv", index=False)

print("Dataset generado")
