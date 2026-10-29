"""Base de conocimiento: reglas de producción SI... ENTONCES...

Fuente: hoja "4_Reglas" de Plantilla_Entrevista_al_Experto_1.xlsx (R0–R10) y hoja
"2. Diseño y Arquitectura SE" de Plantilla_Arquitectura_Sistemas_Expertos.xlsx.

Las reglas son DECLARATIVAS (datos, no código): cada condición indica hecho, operador
y valor. Eso permite al motor:
  * encadenar hacia adelante (de los datos a la alerta),
  * encadenar hacia atrás (de una conclusión a las condiciones que la sostienen),
  * generar el texto "SI... ENTONCES..." automáticamente para la explicación,
  * ajustar umbrales sin tocar el código (los valores "@clave" se leen de UMBRALES).

Reglas añadidas por el prototipo (ver ARQUITECTURA.md, "vacíos revelados"):
  P1, M1 (control del flujo) y R11, R12 (completitud: cubren combinaciones que
  R0–R10 no clasificaban; salen del hecho 12 / pregunta 12 de la entrevista).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Umbrales elicitados en la entrevista (preguntas 3, 4, 5, 6, 8, 9 y 12). Editables en la interfaz.
UMBRALES: dict[str, float] = {
    "prob_rojo": 70.0,        # P(reprobar) ≥ 70 % es crítica (preg. 12)
    "prob_verde": 40.0,       # P(reprobar) < 40 % bien encaminado (preg. 12)
    "asist_baja": 70.0,       # preocupa por debajo de 70 % (preg. 3)
    "asist_alta": 85.0,       # tranquiliza por encima de 85 % (preg. 3)
    "asist_repitente": 80.0,  # repitente con asistencia < 80 % (preg. 8)
    "nota_minima": 3.0,       # nota aprobatoria de laboratorio (preg. 4)
    "nota_buena": 3.5,        # buenas notas (preg. 5)
    "moodle_bajo": 2.0,       # < 2 h/semana en Moodle (preg. 6)
    "moodle_alto": 4.0,       # se conecta mucho (preg. 5)
    "dias_inactividad": 10.0, # 10 días o más sin ingresar (preg. 9)
}

DESCRIPCION_UMBRALES = {
    "prob_rojo": "Probabilidad para ROJO (%)",
    "prob_verde": "Probabilidad para VERDE (%) — por debajo",
    "asist_baja": "Asistencia baja (%) — por debajo",
    "asist_alta": "Asistencia alta (%) — por encima",
    "asist_repitente": "Asistencia mínima repitente (%)",
    "nota_minima": "Nota mínima de laboratorio",
    "nota_buena": "Nota 'buena' de laboratorio",
    "moodle_bajo": "Moodle bajo (h/semana)",
    "moodle_alto": "Moodle alto (h/semana)",
    "dias_inactividad": "Días sin ingreso = inactividad",
}


@dataclass(frozen=True)
class Condicion:
    hecho: str
    op: str                   # '<', '<=', '>', '>=', '==', 'entre', 'existe'
    valor: Any = None         # número, '@umbral', (min, max) o texto
    texto: str = ""           # plantilla legible; {v}, {a}, {b} se reemplazan por los valores


@dataclass(frozen=True)
class Conclusion:
    tipo: str                 # 'asignar' | 'modelo' | 'recalcular_asistencia' | 'candidato'
    texto: str
    hecho: Optional[str] = None
    valor: Any = None         # para 'asignar' puede ser '$otro_hecho'; para 'candidato' el color
    veta_rojo: bool = False   # excepción R7: impide ROJO por asistencia/probabilidad


@dataclass(frozen=True)
class Regla:
    id: str
    nombre: str
    condiciones: tuple[Condicion, ...]
    conclusion: Conclusion
    conector: str = "Y"       # 'Y' (todas) | 'O' (alguna)
    accion: Optional[str] = None
    certeza: str = "Alta"
    origen: str = ""
    prioridad: int = 50       # salience: mayor = se dispara primero
    fase: str = "Clasificación"
    agregada_en_prototipo: bool = False
    veta_por_excepcion: bool = False  # su ROJO se anula si una regla de excepción (R7) se dispara


def resolver(valor: Any, umbrales: dict[str, float]) -> Any:
    if isinstance(valor, str) and valor.startswith("@"):
        return umbrales[valor[1:]]
    if isinstance(valor, tuple):
        return tuple(resolver(v, umbrales) for v in valor)
    return valor


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def texto_condicion(c: Condicion, umbrales: dict[str, float]) -> str:
    v = resolver(c.valor, umbrales)
    if isinstance(v, tuple):
        return c.texto.format(a=_fmt(v[0]), b=_fmt(v[1] - 1 if c.op == "entre" else v[1]))
    return c.texto.format(v=_fmt(v))


def texto_regla(r: Regla, umbrales: dict[str, float]) -> str:
    conector = f" {r.conector} "
    conds = conector.join(texto_condicion(c, umbrales) for c in r.condiciones)
    concl = r.conclusion.texto
    if r.accion:
        concl += f" y {r.accion[0].lower()}{r.accion[1:]}"
    return f"SI {conds} ENTONCES {concl}"


# ---------------------------------------------------------------------------------------
# Condiciones reutilizables
# ---------------------------------------------------------------------------------------
ASIST_BAJA = Condicion("asistencia", "<", "@asist_baja", "la asistencia es < {v} %")
LAB1_BAJO = Condicion("nota_lab1", "<", "@nota_minima", "la nota del laboratorio 1 es < {v}")

REGLAS: tuple[Regla, ...] = (
    # ----------------------------- Fase 1: preparación de hechos -----------------------------
    Regla(
        "P1", "Tomar la asistencia registrada",
        (Condicion("asistencia_bruta", "existe", texto="se conoce la asistencia registrada"),),
        Conclusion("asignar", "tomar la asistencia registrada como asistencia de trabajo",
                   hecho="asistencia", valor="$asistencia_bruta"),
        certeza="Alta", origen="Control del motor", prioridad=100, fase="Preparación",
        agregada_en_prototipo=True,
    ),
    Regla(
        "R8", "Descontar faltas justificadas",
        (Condicion("faltas_justificadas", ">", 0, "hay faltas justificadas registradas"), ASIST_BAJA),
        Conclusion("recalcular_asistencia", "descontar las faltas justificadas y recalcular la asistencia",
                   hecho="asistencia"),
        certeza="Media", origen="Pregunta 7", prioridad=90, fase="Preparación",
    ),
    # ----------------------------- Fase 2: modelo estadístico --------------------------------
    Regla(
        "M1", "Estimar la probabilidad con el historial",
        (Condicion("asistencia", "existe", texto="la asistencia de trabajo está disponible"),),
        Conclusion("modelo", "calcular la probabilidad de reprobar con el modelo entrenado con cohortes anteriores",
                   hecho="prob_reprobar"),
        certeza="Alta", origen="Hoja 2 (Técnica: modelos estadísticos)", prioridad=80, fase="Modelo",
        agregada_en_prototipo=True,
    ),
    # ----------------------------- Fase 3: clasificación (R0–R10) ----------------------------
    Regla(
        "R0", "Baja asistencia, laboratorio 1 perdido y poca conexión",
        (ASIST_BAJA, LAB1_BAJO,
         Condicion("horas_moodle_semana", "<=", "@moodle_bajo", "hay {v} horas o menos de conexión a Moodle por semana")),
        Conclusion("candidato", "semáforo ROJO", valor="ROJO"),
        accion="Avisar al docente antes de la semana 4",
        certeza="Alta", origen="Pregunta 1 (caso 0)", prioridad=60, veta_por_excepcion=True,
    ),
    Regla(
        "R1", "Baja asistencia y laboratorio 1 perdido",
        (ASIST_BAJA, LAB1_BAJO),
        Conclusion("candidato", "riesgo ROJO", valor="ROJO"),
        accion="Citar a tutoría individual antes de la semana 4",
        certeza="Alta", origen="Pregunta 1", prioridad=55, veta_por_excepcion=True,
    ),
    Regla(
        "R2", "Probabilidad de reprobar crítica",
        (Condicion("prob_reprobar", ">=", "@prob_rojo", "la probabilidad de reprobar es ≥ {v} %"),),
        Conclusion("candidato", "semáforo ROJO", valor="ROJO"),
        accion="Citar a tutoría individual",
        certeza="Alta", origen="Pregunta 12", prioridad=55, veta_por_excepcion=True,
    ),
    Regla(
        "R3", "Riesgo moderado y poca conexión a Moodle",
        (Condicion("prob_reprobar", "entre", ("@prob_verde", "@prob_rojo"),
                   "la probabilidad de reprobar está entre {a} % y {b} %"),
         Condicion("horas_moodle_semana", "<", "@moodle_bajo", "la conexión a Moodle es < {v} horas/semana")),
        Conclusion("candidato", "semáforo AMARILLO", valor="AMARILLO"),
        accion="Monitoreo semanal",
        certeza="Alta", origen="Pregunta 6",
    ),
    Regla(
        "R4", "Riesgo bajo y buena asistencia",
        (Condicion("prob_reprobar", "<", "@prob_verde", "la probabilidad de reprobar es < {v} %"),
         Condicion("asistencia", ">", "@asist_alta", "la asistencia es > {v} %")),
        Conclusion("candidato", "semáforo VERDE", valor="VERDE"),
        accion="Seguimiento normal",
        certeza="Alta", origen="Pregunta 3",
    ),
    Regla(
        "R5", "Buena asistencia pero laboratorio 1 perdido",
        (Condicion("asistencia", ">=", "@asist_baja", "la asistencia es ≥ {v} %"), LAB1_BAJO),
        Conclusion("candidato", "semáforo AMARILLO", valor="AMARILLO"),
        accion="Refuerzo en punteros y memoria dinámica",
        certeza="Alta", origen="Pregunta 4",
    ),
    Regla(
        "R7", "Excepción: asiste poco pero rinde bien",
        (ASIST_BAJA,
         Condicion("horas_moodle_semana", ">=", "@moodle_alto", "la conexión a Moodle es ≥ {v} horas/semana"),
         Condicion("nota_lab1", ">=", "@nota_buena", "la nota del laboratorio 1 es ≥ {v}")),
        Conclusion("candidato", "semáforo AMARILLO (no ROJO)", valor="AMARILLO", veta_rojo=True),
        accion="Consultar la causa externa antes de actuar",
        certeza="Media", origen="Pregunta 5", prioridad=58,
    ),
    Regla(
        "R9", "Repite la materia y falta a clase",
        (Condicion("repite_materia", "==", True, "el estudiante repite la materia"),
         Condicion("asistencia", "<", "@asist_repitente", "la asistencia es < {v} %")),
        Conclusion("candidato", "semáforo AMARILLO", valor="AMARILLO"),
        certeza="Media", origen="Pregunta 8",
    ),
    Regla(
        "R10", "Inactivo en Moodle o con laboratorios pendientes",
        (Condicion("dias_sin_ingreso_moodle", ">=", "@dias_inactividad", "hay {v} días o más sin ingreso a Moodle"),
         Condicion("labs_sin_entregar", ">=", 1, "hay un laboratorio sin entregar")),
        Conclusion("candidato", "semáforo AMARILLO", valor="AMARILLO"),
        conector="O",
        accion="Contactar al estudiante esta semana",
        certeza="Media", origen="Pregunta 9",
    ),
    # ----------------------------- Fase 4: escalamiento --------------------------------------
    Regla(
        "R6", "También perdió el laboratorio 2",
        (Condicion("semaforo_provisional", "==", "AMARILLO", "el semáforo es AMARILLO"),
         Condicion("nota_lab2", "<", "@nota_minima", "la nota del laboratorio 2 es < {v}")),
        Conclusion("candidato", "subir el semáforo a ROJO", valor="ROJO"),
        accion="Citar a tutoría individual antes de la semana 4",
        certeza="Media", origen="Pregunta 4", prioridad=40, fase="Escalamiento",
    ),
    # ----------------------------- Fase 5: completitud (agregadas) ---------------------------
    Regla(
        "R11", "Riesgo moderado sin otras señales",
        (Condicion("n_candidatos", "==", 0, "ninguna otra regla clasificó al estudiante"),
         Condicion("prob_reprobar", "entre", ("@prob_verde", "@prob_rojo"),
                   "la probabilidad de reprobar está entre {a} % y {b} %")),
        Conclusion("candidato", "semáforo AMARILLO", valor="AMARILLO"),
        accion="Seguimiento semanal",
        certeza="Media", origen="Hecho 12 / Pregunta 12", prioridad=10, fase="Completitud",
        agregada_en_prototipo=True,
    ),
    Regla(
        "R12", "Riesgo bajo sin otras señales",
        (Condicion("n_candidatos", "==", 0, "ninguna otra regla clasificó al estudiante"),
         Condicion("prob_reprobar", "<", "@prob_verde", "la probabilidad de reprobar es < {v} %")),
        Conclusion("candidato", "semáforo VERDE", valor="VERDE"),
        accion="Seguimiento normal",
        certeza="Media", origen="Hecho 12 / Pregunta 12", prioridad=10, fase="Completitud",
        agregada_en_prototipo=True,
    ),
)

REGLAS_POR_ID = {r.id: r for r in REGLAS}

# Hechos derivados y la regla (o componente) que los produce — usado por el encadenamiento hacia atrás
PRODUCTORES = {
    "asistencia": ["R8", "P1"],
    "prob_reprobar": ["M1"],
}

ETIQUETAS_HECHOS = {
    "asistencia_bruta": "Asistencia registrada (%)",
    "asistencia": "Asistencia de trabajo (%)",
    "faltas_justificadas": "Faltas justificadas",
    "horas_moodle_semana": "Horas en Moodle / semana",
    "dias_sin_ingreso_moodle": "Días sin ingresar a Moodle",
    "nota_lab1": "Nota laboratorio 1",
    "nota_lab2": "Nota laboratorio 2",
    "labs_sin_entregar": "Laboratorios sin entregar",
    "puntaje_admision_mat": "Puntaje admisión (matemáticas)",
    "repite_materia": "Repite la materia",
    "trabaja_tiempo_completo": "Trabaja tiempo completo",
    "prob_reprobar": "Probabilidad de reprobar (%)",
    "semaforo_provisional": "Semáforo provisional",
    "n_candidatos": "Conclusiones candidatas",
}
