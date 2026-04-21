# PredictPlast AI

Plataforma de mantenimiento predictivo para inyectoras de plástico.

## Descripción

PredictPlast AI es un proyecto centrado en el desarrollo de un sistema capaz de analizar datos de inyectoras de plástico para detectar anomalías, anticipar posibles fallos y ayudar a optimizar el mantenimiento industrial.

El objetivo inicial es construir un MVP sencillo pero funcional utilizando datos simulados, modelos básicos de detección de anomalías y una visualización clara del estado de la máquina.

## Problema que resuelve

Las empresas que utilizan inyectoras de plástico sufren pérdidas por:

* Paradas inesperadas
* Scrap y defectos de producción
* Costes energéticos elevados
* Mantenimiento reactivo

PredictPlast AI busca detectar comportamientos anómalos antes de que se conviertan en un fallo real.

## Objetivo a 3 meses

Desarrollar un sistema básico que:

* Genere o utilice datos simulados de una inyectora
* Detecte anomalías simples
* Muestre el estado de la máquina
* Incluya una visualización clara
* Sea enseñable como proyecto de portfolio

## Resultado visible esperado

"Tengo un pequeño sistema que analiza datos de una inyectora y detecta anomalías antes de que se produzca un fallo."

## Stack tecnológico inicial

* Python
* Pandas
* NumPy
* Matplotlib
* Scikit-learn
* Jupyter Notebook
* Git
* GitHub

## Estructura inicial del proyecto

```text
PredictPlast-AI/
├── data/
│   ├── raw/
│   └── processed/
│
├── images/
│
├── notebooks/
│
├── src/
│   ├── data_generation.py
│   ├── preprocessing.py
│   ├── anomaly_detection.py
│   └── visualization.py
│
├── README.md
├── requirements.txt
└── .gitignore
```

## Roadmap inicial

### Mes 1

* Comprender el problema
* Definir variables
* Crear dataset simulado
* Explorar y limpiar datos

### Mes 2

* Implementar modelo de anomalías
* Generar outputs entendibles
* Crear visualizaciones

### Mes 3

* Mejorar robustez
* Preparar demo
* Documentar el proyecto
* Dejarlo listo para portfolio

## Variables iniciales de la inyectora

* Temperatura
* Presión
* Tiempo de ciclo
* Número de ciclos
* Paradas
* Consumo energético

## Próximos pasos

1. Crear la estructura de carpetas
2. Hacer el primer commit
3. Generar el primer dataset simulado
4. Crear las primeras gráficas
5. Empezar el modelo de detección de anomalías
6. 