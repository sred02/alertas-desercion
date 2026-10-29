"""Sistema Experto de Alertas Tempranas en Ciencias Básicas (C++ y Estructuras de Datos).

Paquete del prototipo. Cada módulo corresponde a un componente de la arquitectura:

- ontologia.py           -> Ontología del dominio (entidades, relaciones, taxonomía de riesgo)
- ingesta_simulada.py    -> Adaptador de datos (Moodle / sistema de notas SIMULADOS)
- modelo_estadistico.py  -> Modelo estadístico entrenado con cohortes anteriores
- base_conocimiento.py   -> Base de reglas de producción (SI... ENTONCES...) del Excel
- motor_inferencia.py    -> Motor de inferencia (encadenamiento hacia adelante + hacia atrás)
- explicacion.py         -> Módulo de explicación (¿por qué? / ¿por qué no?)
- sistema.py             -> Fachada que orquesta el flujo completo
"""

__version__ = "1.0.0"
