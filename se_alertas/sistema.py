"""Fachada del sistema experto: orquesta ingesta -> hechos -> motor -> alertas."""

from __future__ import annotations

import math
from typing import Iterable, Optional

import pandas as pd

from .explicacion import resumen_corto
from .modelo_estadistico import ModeloRiesgo
from .motor_inferencia import MotorInferencia, ResultadoInferencia


def _nota(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


def hechos_desde_fila(fila: dict) -> dict:
    """Base de hechos inicial de un estudiante (lo que llega desde Moodle / sistema de notas)."""
    lab1, lab2 = _nota(fila.get("nota_lab1")), _nota(fila.get("nota_lab2"))
    programadas = int(fila["sesiones_programadas"])
    asistidas = int(fila["sesiones_asistidas"])
    return {
        "sesiones_programadas": programadas,
        "sesiones_asistidas": asistidas,
        "faltas_justificadas": int(fila["faltas_justificadas"]),
        "asistencia_bruta": round(100.0 * asistidas / max(programadas, 1), 1),
        "horas_moodle_semana": float(fila["horas_moodle_semana"]),
        "dias_sin_ingreso_moodle": int(fila["dias_sin_ingreso_moodle"]),
        "nota_lab1": lab1,
        "nota_lab2": lab2,
        "labs_sin_entregar": int(lab1 is None) + int(lab2 is None),
        "puntaje_admision_mat": float(fila["puntaje_admision_mat"]),
        "repite_materia": bool(fila["repite_materia"]),
        "trabaja_tiempo_completo": bool(fila["trabaja_tiempo_completo"]),
    }


class SistemaExperto:
    def __init__(self, modelo: ModeloRiesgo, umbrales: Optional[dict] = None,
                 reglas_activas: Optional[Iterable[str]] = None):
        self.modelo = modelo
        self.motor = MotorInferencia(modelo, umbrales, reglas_activas)

    def evaluar_estudiante(self, fila: dict) -> ResultadoInferencia:
        return self.motor.encadenar_adelante(hechos_desde_fila(fila))

    def evaluar_curso(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, ResultadoInferencia]]:
        resultados: dict[str, ResultadoInferencia] = {}
        filas = []
        for fila in df.to_dict("records"):
            res = self.evaluar_estudiante(fila)
            resultados[fila["id"]] = res
            filas.append(
                {
                    "id": fila["id"],
                    "nombre": fila["nombre"],
                    "curso": fila["curso"],
                    "grupo": fila["grupo"],
                    "semaforo": res.semaforo.value,
                    "prob_reprobar": res.probabilidad,
                    "asistencia": res.memoria["asistencia"],
                    "horas_moodle": res.memoria["horas_moodle_semana"],
                    "nota_lab1": res.memoria["nota_lab1"],
                    "nota_lab2": res.memoria["nota_lab2"],
                    "regla_decisiva": res.regla_decisiva,
                    "reglas_disparadas": " → ".join(res.reglas_disparadas),
                    "accion": res.acciones[0],
                    "acciones_especificas": "; ".join(res.acciones[1:]),
                    "certeza": res.certeza,
                    "justificacion": resumen_corto(res, self.motor),
                }
            )
        orden = {"ROJO": 0, "AMARILLO": 1, "VERDE": 2}
        tabla = pd.DataFrame(filas)
        tabla = tabla.sort_values(["semaforo", "prob_reprobar"], key=lambda s: s.map(orden) if s.name == "semaforo" else -s)
        return tabla.reset_index(drop=True), resultados
