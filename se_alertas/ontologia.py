"""Ontología del dominio (hoja "2. Diseño y Arquitectura SE" del Excel).

Entidades: Estudiante, Curso, SesionClase, Laboratorio, ActividadMoodle, Alerta, Docente.
Relaciones: el estudiante CURSA un curso, ASISTE a sesiones, PRESENTA laboratorios,
GENERA actividad en Moodle y RECIBE alertas que ATIENDE el docente.
Taxonomía de riesgo: ALTO (ROJO) > MEDIO (AMARILLO) > BAJO (VERDE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Semaforo(str, Enum):
    """Taxonomía de riesgo. El orden numérico se usa para resolver conflictos (prudencia)."""

    VERDE = "VERDE"
    AMARILLO = "AMARILLO"
    ROJO = "ROJO"

    @property
    def severidad(self) -> int:
        return {"VERDE": 0, "AMARILLO": 1, "ROJO": 2}[self.value]

    @property
    def nivel_riesgo(self) -> str:
        return {"VERDE": "Bajo", "AMARILLO": "Medio", "ROJO": "Alto"}[self.value]

    @property
    def accion_base(self) -> str:
        # Procedimiento de intervención (entrevista, pregunta 10)
        return {
            "ROJO": "Tutoría individual antes de la semana 4",
            "AMARILLO": "Seguimiento semanal y refuerzo del tema",
            "VERDE": "Seguimiento normal",
        }[self.value]


@dataclass
class Curso:
    codigo: str
    nombre: str
    grupo: str
    docente: str


@dataclass
class Laboratorio:
    numero: int
    tema: str
    entregado: bool
    nota: Optional[float]  # None = sin entregar / sin calificar


@dataclass
class Estudiante:
    """Hechos de un estudiante en un corte semanal (una fila por estudiante y semana)."""

    id: str
    nombre: str
    curso: str
    grupo: str
    semana_corte: int
    # Asistencia (sesiones de clase)
    sesiones_programadas: int
    sesiones_asistidas: int
    faltas_justificadas: int
    # Actividad Moodle
    horas_moodle_semana: float
    dias_sin_ingreso_moodle: int
    # Laboratorios prácticos
    nota_lab1: Optional[float]
    nota_lab2: Optional[float]
    # Perfil de ingreso
    puntaje_admision_mat: float
    repite_materia: bool
    trabaja_tiempo_completo: bool
    jornada: str = "Diurna"
    tipo_colegio: str = "Público"

    @property
    def asistencia_pct(self) -> float:
        if self.sesiones_programadas <= 0:
            return 100.0
        return round(100.0 * self.sesiones_asistidas / self.sesiones_programadas, 1)


@dataclass
class Alerta:
    """Resultado que el sistema entrega al docente para un estudiante."""

    estudiante_id: str
    semaforo: Semaforo
    probabilidad_reprobar: float
    reglas_disparadas: list[str] = field(default_factory=list)
    acciones: list[str] = field(default_factory=list)
    certeza: str = "Alta"


# Diccionario de conceptos del dominio (glosario visible en la interfaz)
GLOSARIO = {
    "Mortalidad académica": "Proporción de estudiantes que reprueban el curso.",
    "Deserción": "Abandono del curso o del programa antes de terminar el semestre.",
    "Inactividad": "10 días o más sin ingresar a Moodle, o un laboratorio sin entregar.",
    "Desbordamiento de memoria": "Error típico de C++ (acceso fuera de límites / fuga de memoria); "
    "tema del laboratorio 1 y principal indicador de dificultad conceptual.",
    "Asistencia ajustada": "Asistencia recalculada descontando faltas justificadas (regla R8).",
    "Probabilidad de reprobar": "Salida del modelo estadístico entrenado con cohortes anteriores (0–100 %).",
    "Semáforo provisional": "Color más severo entre las conclusiones candidatas en un ciclo de inferencia.",
}

# Relaciones de la ontología (para documentación y la pestaña de arquitectura)
RELACIONES = [
    ("Estudiante", "cursa", "Curso"),
    ("Curso", "es dictado por", "Docente"),
    ("Estudiante", "asiste a", "Sesión de clase"),
    ("Estudiante", "presenta", "Laboratorio"),
    ("Estudiante", "genera", "Actividad Moodle"),
    ("Estudiante", "recibe", "Alerta"),
    ("Docente", "atiende", "Alerta"),
    ("Alerta", "se clasifica como", "Semáforo (Rojo / Amarillo / Verde)"),
]
