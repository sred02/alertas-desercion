"""Adaptador de ingesta de datos — 100 % SIMULADO (mock de Moodle y del sistema de notas).

En producción este componente se conectaría a la API de Moodle (web services
core_course_get_contents, gradereport_user_get_grade_items, logs de acceso) y al
sistema académico. En el prototipo se reemplaza por generadores sintéticos con
semilla fija para que cualquier evaluador obtenga los mismos resultados.

Todos los nombres son FICTICIOS, generados al azar.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------------------
# Esquema de datos (contrato entre la ingesta y el resto del sistema)
# --------------------------------------------------------------------------------------
COLUMNAS_ESTUDIANTE = [
    "id",
    "nombre",
    "curso",
    "grupo",
    "semana_corte",
    "sesiones_programadas",
    "sesiones_asistidas",
    "faltas_justificadas",
    "horas_moodle_semana",
    "dias_sin_ingreso_moodle",
    "nota_lab1",
    "nota_lab2",
    "puntaje_admision_mat",
    "repite_materia",
    "trabaja_tiempo_completo",
    "jornada",
    "tipo_colegio",
]

CURSOS = [
    ("Programación en C++", "G1", "Doc. Programación A"),
    ("Programación en C++", "G2", "Doc. Programación B"),
    ("Estructuras de Datos", "G1", "Doc. Estructuras A"),
    ("Estructuras de Datos", "G2", "Doc. Estructuras B"),
]

LABS = {
    1: "Punteros y memoria dinámica (desbordamiento de memoria)",
    2: "Pilas con arreglos dinámicos",
}

SESIONES_POR_SEMANA = 4  # 2 clases teóricas + 2 sesiones de laboratorio

_NOMBRES = [
    "Valentina", "Santiago", "Mariana", "Juan José", "Isabella", "Samuel", "Sofía", "Matías",
    "Daniela", "Alejandro", "Camila", "Sebastián", "Laura", "Nicolás", "Manuela", "Tomás",
    "Sara", "Emmanuel", "Luciana", "David", "Gabriela", "Andrés", "Salomé", "Esteban",
    "Juliana", "Miguel Ángel", "Antonella", "Felipe", "Valeria", "Julián", "María José", "Kevin",
    "Paula", "Jerónimo", "Ana Sofía", "Cristian", "Melissa", "Brayan", "Natalia", "Mateo",
]
_APELLIDOS = [
    "Restrepo", "Gómez", "Henao", "Zapata", "Ospina", "Arango", "Vélez", "Cardona", "Mejía",
    "Correa", "Giraldo", "Montoya", "Agudelo", "Castaño", "Quintero", "Muñoz", "Ríos", "Cano",
    "Echeverri", "Betancur", "Valencia", "Londoño", "Uribe", "Jaramillo", "Patiño", "Salazar",
    "Hoyos", "Toro", "Builes", "Álvarez", "Duque", "Marín", "Rendón", "Posada", "Sierra",
]


def _sigmoide(x):
    return 1.0 / (1.0 + np.exp(-x))


def _generar_bloque(n: int, rng: np.random.Generator, semana_corte: int = 3) -> pd.DataFrame:
    """Genera n estudiantes con variables correlacionadas a dos rasgos latentes:
    compromiso (asistencia, Moodle, entregas) y habilidad (laboratorios, admisión)."""
    compromiso = rng.normal(0, 1, n)
    habilidad = rng.normal(0, 1, n)

    trabaja = rng.random(n) < _sigmoide(-0.9 - 0.4 * compromiso)
    repite = rng.random(n) < _sigmoide(-1.7 - 0.6 * habilidad)
    jornada = np.where(trabaja & (rng.random(n) < 0.7), "Nocturna", "Diurna")
    colegio = np.where(rng.random(n) < 0.68, "Público", "Privado")

    programadas = np.full(n, SESIONES_POR_SEMANA * semana_corte)
    p_asistir = np.clip(0.85 + 0.09 * compromiso - 0.06 * trabaja + rng.normal(0, 0.05, n), 0.25, 0.99)
    asistidas = rng.binomial(programadas, p_asistir)
    faltas = programadas - asistidas
    justificadas = rng.binomial(faltas, 0.18)

    horas = np.clip(3.4 + 1.5 * compromiso + 0.3 * habilidad + rng.normal(0, 1.0, n), 0.0, 12.0).round(1)
    dias_sin = np.clip(np.round(14 * np.exp(-0.45 * horas) + rng.normal(0, 1.5, n)), 0, 21).astype(int)

    puntaje = np.clip(62 + 11 * habilidad + rng.normal(0, 8, n), 20, 100).round(0)

    lab1 = np.clip(3.3 + 0.75 * habilidad + 0.25 * compromiso + rng.normal(0, 0.55, n), 0.0, 5.0).round(1)
    lab2 = np.clip(lab1 + 0.15 * compromiso + rng.normal(0, 0.45, n) - 0.1, 0.0, 5.0).round(1)
    entrega1 = rng.random(n) < _sigmoide(3.8 + 1.4 * compromiso)
    entrega2 = rng.random(n) < _sigmoide(3.4 + 1.4 * compromiso)
    lab1 = np.where(entrega1, lab1, np.nan)
    lab2 = np.where(entrega2, lab2, np.nan)

    return pd.DataFrame(
        {
            "semana_corte": semana_corte,
            "sesiones_programadas": programadas,
            "sesiones_asistidas": asistidas,
            "faltas_justificadas": justificadas,
            "horas_moodle_semana": horas,
            "dias_sin_ingreso_moodle": dias_sin,
            "nota_lab1": lab1,
            "nota_lab2": lab2,
            "puntaje_admision_mat": puntaje,
            "repite_materia": repite,
            "trabaja_tiempo_completo": trabaja,
            "jornada": jornada,
            "tipo_colegio": colegio,
        }
    )


def _nombres_ficticios(n: int, rng: np.random.Generator) -> list[str]:
    usados: set[str] = set()
    salida = []
    while len(salida) < n:
        ap1, ap2 = rng.choice(_APELLIDOS, size=2, replace=False)
        nombre = f"{rng.choice(_NOMBRES)} {ap1} {ap2}"
        if nombre not in usados:
            usados.add(nombre)
            salida.append(nombre)
    return salida


def _resultado_real(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """'Verdad de campo' de las cohortes históricas: si el estudiante reprobó (1) o aprobó (0).
    Proceso latente desconocido para el sistema; el modelo estadístico debe aprenderlo."""
    asist = df["sesiones_asistidas"] / (df["sesiones_programadas"] - df["faltas_justificadas"]).clip(lower=1)
    lab1 = df["nota_lab1"].fillna(0.0)
    lab2 = df["nota_lab2"].fillna(0.0)
    z = (
        -0.95
        + 3.6 * (0.80 - asist)
        + 0.28 * (3.0 - df["horas_moodle_semana"])
        + 0.85 * (3.0 - lab1)
        + 0.60 * (3.0 - lab2)
        + 0.95 * df["repite_materia"].astype(float)
        + 0.45 * df["trabaja_tiempo_completo"].astype(float)
        + 0.025 * (60 - df["puntaje_admision_mat"])
        + 0.06 * (df["dias_sin_ingreso_moodle"] - 4)
        + rng.normal(0, 0.7, len(df))
    )
    return (rng.random(len(df)) < _sigmoide(z)).astype(int)


# --------------------------------------------------------------------------------------
# API pública del adaptador
# --------------------------------------------------------------------------------------
@dataclass
class FuenteMoodleSimulada:
    """Mock del LMS. Mismo contrato que tendría un conector real a Moodle."""

    semilla: int = 2026
    semana_corte: int = 3

    def cohortes_historicas(self, cohortes=("2023-1", "2023-2", "2024-1", "2024-2", "2025-1", "2025-2"),
                            por_cohorte: int = 200) -> pd.DataFrame:
        rng = np.random.default_rng(self.semilla)
        bloques = []
        for c in cohortes:
            b = _generar_bloque(por_cohorte, rng, self.semana_corte)
            b.insert(0, "cohorte", c)
            b["reprobo"] = _resultado_real(b, rng)
            bloques.append(b)
        return pd.concat(bloques, ignore_index=True)

    def curso_actual(self, n_estudiantes: int = 160, periodo: str = "2026-2") -> pd.DataFrame:
        rng = np.random.default_rng(self.semilla + 1)
        df = _generar_bloque(n_estudiantes, rng, self.semana_corte)
        grupos = rng.integers(0, len(CURSOS), n_estudiantes)
        df.insert(0, "id", [f"EST-{periodo[:4]}{i + 1:04d}" for i in range(n_estudiantes)])
        df.insert(1, "nombre", _nombres_ficticios(n_estudiantes, rng))
        df.insert(2, "curso", [CURSOS[g][0] for g in grupos])
        df.insert(3, "grupo", [CURSOS[g][1] for g in grupos])
        return df[COLUMNAS_ESTUDIANTE]


def cargar_csv(contenido: bytes) -> pd.DataFrame:
    """Permite al evaluador cargar sus propios datos (mismo esquema que la plantilla)."""
    df = pd.read_csv(io.BytesIO(contenido))
    faltantes = [c for c in COLUMNAS_ESTUDIANTE if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas en el CSV: {', '.join(faltantes)}")
    for col in ("repite_materia", "trabaja_tiempo_completo"):
        df[col] = df[col].astype(str).str.strip().str.lower().isin(["1", "true", "si", "sí", "verdadero"])
    for col in ("nota_lab1", "nota_lab2"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[COLUMNAS_ESTUDIANTE]


def plantilla_csv() -> bytes:
    """CSV de ejemplo (5 filas) para que el evaluador vea el formato esperado."""
    ejemplo = FuenteMoodleSimulada(semilla=7).curso_actual(5)
    return ejemplo.to_csv(index=False).encode("utf-8")
