"""Módulo de explicación.

Dos niveles de lectura:
  * Para el docente: motivos en lenguaje natural, sin códigos de regla
    ("Asiste al 58 % de las clases y obtuvo 1,8 en el laboratorio 1").
  * Para el evaluador: árbol de encadenamiento hacia atrás (¿por qué? / ¿por qué no?)
    y la secuencia de reglas aplicadas, con sus identificadores.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from .base_conocimiento import ETIQUETAS_HECHOS
from .motor_inferencia import MotorInferencia, ResultadoInferencia

NIVEL = {"ROJO": "Riesgo alto", "AMARILLO": "Riesgo medio", "VERDE": "Riesgo bajo"}


# ----------------------------------------------------------------------------- formato de valores
def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def pct(v: float) -> str:
    """Probabilidad legible: entero, sin prometer 0 % ni 100 %."""
    if _vacio(v):
        return "sin dato"
    if v < 1:
        return "menos de 1 %"
    if v > 99:
        return "más de 99 %"
    return f"{round(v):.0f} %"


def nota(v: Any) -> str:
    return "sin entregar" if _vacio(v) else f"{v:.1f}".replace(".", ",")


def horas(v: float) -> str:
    texto = f"{v:.1f}".replace(".", ",").replace(",0", "")
    return f"{texto} hora por semana" if v == 1 else f"{texto} horas por semana"


def fmt(hecho: str, v: Any) -> str:
    """Valor de un hecho tal como se muestra en la interfaz."""
    if _vacio(v):
        return "sin entregar" if hecho.startswith("nota_lab") else "sin dato"
    if hecho == "prob_reprobar":
        return pct(v)
    if hecho in ("asistencia", "asistencia_bruta"):
        return f"{v:.0f} %"
    if hecho.startswith("nota_lab"):
        return nota(v)
    if hecho == "horas_moodle_semana":
        return horas(v)
    if hecho == "dias_sin_ingreso_moodle":
        return f"{int(v)} días"
    if isinstance(v, bool):
        return "Sí" if v else "No"
    if hecho == "semaforo_provisional":
        return NIVEL.get(v, "sin clasificar").lower()
    return str(v)


def etiqueta(hecho: str) -> str:
    return ETIQUETAS_HECHOS.get(hecho, hecho)


# ----------------------------------------------------------------------------- motivos en lenguaje natural
def _r10(h: dict, u: dict) -> str:
    partes = []
    if not _vacio(h.get("dias_sin_ingreso_moodle")) and h["dias_sin_ingreso_moodle"] >= u["dias_inactividad"]:
        partes.append(f"lleva {int(h['dias_sin_ingreso_moodle'])} días sin ingresar a Moodle")
    k = h.get("labs_sin_entregar") or 0
    if k >= 1:
        partes.append("tiene un laboratorio sin entregar" if k == 1 else f"tiene {k} laboratorios sin entregar")
    texto = " y ".join(partes) or "muestra inactividad"
    return texto[0].upper() + texto[1:] + "."


MOTIVOS: dict[str, Callable[[dict, dict], str]] = {
    "R0": lambda h, u: (f"Asiste al {fmt('asistencia', h['asistencia'])} de las clases, obtuvo {nota(h['nota_lab1'])} "
                        f"en el laboratorio 1 y se conecta {horas(h['horas_moodle_semana'])} a Moodle."),
    "R1": lambda h, u: (f"Asiste al {fmt('asistencia', h['asistencia'])} de las clases y obtuvo "
                        f"{nota(h['nota_lab1'])} en el laboratorio 1."),
    "R2": lambda h, u: (f"Comparado con estudiantes de semestres anteriores, su probabilidad de reprobar "
                        f"es muy alta ({pct(h['prob_reprobar'])})."),
    "R3": lambda h, u: (f"Su probabilidad de reprobar es moderada ({pct(h['prob_reprobar'])}) y se conecta "
                        f"poco a Moodle ({horas(h['horas_moodle_semana'])})."),
    "R4": lambda h, u: (f"Su probabilidad de reprobar es baja ({pct(h['prob_reprobar'])}) y asiste al "
                        f"{fmt('asistencia', h['asistencia'])} de las clases."),
    "R5": lambda h, u: (f"Asiste con regularidad ({fmt('asistencia', h['asistencia'])}), pero obtuvo "
                        f"{nota(h['nota_lab1'])} en el laboratorio de punteros y memoria dinámica."),
    "R7": lambda h, u: (f"Asiste solo al {fmt('asistencia', h['asistencia'])} de las clases, pero trabaja en Moodle "
                        f"({horas(h['horas_moodle_semana'])}) y obtuvo {nota(h['nota_lab1'])} en el laboratorio 1. "
                        f"La inasistencia puede tener una causa externa."),
    "R9": lambda h, u: f"Repite la materia y asiste al {fmt('asistencia', h['asistencia'])} de las clases.",
    "R10": _r10,
    "R6": lambda h, u: f"Tampoco aprobó el laboratorio 2 ({nota(h['nota_lab2'])}), por eso el riesgo sube a alto.",
    "R11": lambda h, u: f"Su probabilidad de reprobar es moderada ({pct(h['prob_reprobar'])}).",
    "R12": lambda h, u: f"Su probabilidad de reprobar es baja ({pct(h['prob_reprobar'])}).",
}


def _r10_corto(h: dict, u: dict) -> str:
    partes = []
    if not _vacio(h.get("dias_sin_ingreso_moodle")) and h["dias_sin_ingreso_moodle"] >= u["dias_inactividad"]:
        partes.append(f"{int(h['dias_sin_ingreso_moodle'])} días sin entrar a Moodle")
    if (h.get("labs_sin_entregar") or 0) >= 1:
        partes.append("laboratorio sin entregar")
    return (" y ".join(partes) or "inactividad").capitalize()


CORTOS: dict[str, Callable[[dict, dict], str]] = {
    "R0": lambda h, u: (f"Asistencia {fmt('asistencia', h['asistencia'])}, laboratorio 1 con {nota(h['nota_lab1'])} "
                        f"y poca conexión"),
    "R1": lambda h, u: f"Asistencia {fmt('asistencia', h['asistencia'])} y laboratorio 1 con {nota(h['nota_lab1'])}",
    "R2": lambda h, u: "Probabilidad de reprobar muy alta",
    "R3": lambda h, u: "Riesgo moderado y poca conexión a Moodle",
    "R4": lambda h, u: f"Riesgo bajo y asistencia {fmt('asistencia', h['asistencia'])}",
    "R5": lambda h, u: f"Asiste, pero laboratorio 1 con {nota(h['nota_lab1'])}",
    "R7": lambda h, u: "Asiste poco, pero rinde bien",
    "R9": lambda h, u: f"Repite la materia, asistencia {fmt('asistencia', h['asistencia'])}",
    "R10": _r10_corto,
    "R6": lambda h, u: f"Laboratorio 2 también perdido ({nota(h['nota_lab2'])})",
    "R11": lambda h, u: "Riesgo moderado",
    "R12": lambda h, u: "Riesgo bajo",
}


def _hechos_al_disparar(res: ResultadoInferencia, regla_id: str) -> dict:
    disparo = next((d for d in res.traza if d.regla == regla_id), None)
    return {**res.memoria, **(disparo.hechos_usados if disparo else {})}


def motivo(res: ResultadoInferencia, motor: MotorInferencia, regla_id: str) -> str:
    return MOTIVOS[regla_id](_hechos_al_disparar(res, regla_id), motor.umbrales)


def _escalado(res: ResultadoInferencia) -> bool:
    return any(c.regla == "R6" and not c.anulado for c in res.candidatos) and res.semaforo.value == "ROJO"


def motivos(res: ResultadoInferencia, motor: MotorInferencia) -> list[str]:
    """Razones que sostienen el resultado final, en el orden en que se dedujeron.
    Si el riesgo subió por R6, primero van las señales de riesgo medio que llevaron a ese escalamiento."""
    ids = [c.regla for c in res.candidatos if c.color == res.semaforo.value and not c.anulado]
    if _escalado(res):
        previas = [c.regla for c in res.candidatos if c.color == "AMARILLO" and not c.anulado]
        ids = [i for i in ids if i != "R6"] + previas + ["R6"]
    # Si las condiciones de una regla están contenidas en otra que también se aplicó (R1 dentro de R0),
    # su motivo sería repetido: se omite.
    conds = {i: set(motor.por_id[i].condiciones) for i in ids}
    ids = [i for i in ids if not any(j != i and conds[i] < conds[j] for j in ids)]
    salida = []
    for rid in ids:
        if rid in MOTIVOS:
            texto = motivo(res, motor, rid)
            if texto not in salida:
                salida.append(texto)
    return salida


def senales_adicionales(res: ResultadoInferencia, motor: MotorInferencia) -> list[str]:
    """Otras señales detectadas que no definieron el resultado."""
    usados = set(motivos(res, motor))
    salida = []
    for c in res.candidatos:
        if c.color != res.semaforo.value and not c.anulado and c.regla in MOTIVOS:
            texto = motivo(res, motor, c.regla)
            if texto not in usados and texto not in salida:
                salida.append(texto)
    return salida


def ajustes(res: ResultadoInferencia) -> list[str]:
    m = res.memoria
    if "R8" in res.reglas_disparadas:
        k = m["faltas_justificadas"]
        faltas = "una falta justificada" if k == 1 else f"{k} faltas justificadas"
        return [f"Se descontaron {faltas}: la asistencia considerada es {fmt('asistencia', m['asistencia'])} "
                f"(registrada: {fmt('asistencia', m['asistencia_bruta'])})."]
    return []


def motivo_principal(res: ResultadoInferencia, motor: MotorInferencia) -> str:
    """Motivo breve para la tabla (máximo dos señales)."""
    ids = [c.regla for c in res.candidatos if c.color == res.semaforo.value and not c.anulado]
    if _escalado(res):
        previas = [c.regla for c in res.candidatos if c.color == "AMARILLO" and not c.anulado]
        ids = previas[:1] + ["R6"]
    conds = {i: set(motor.por_id[i].condiciones) for i in ids}
    ids = [i for i in ids if not any(j != i and conds[i] < conds[j] for j in ids)]
    textos = []
    for rid in ids:
        if rid in CORTOS:
            t = CORTOS[rid](_hechos_al_disparar(res, rid), motor.umbrales)
            if t not in textos:
                textos.append(t)
    return "; ".join(textos[:2])


def resumen_tecnico(res: ResultadoInferencia, motor: MotorInferencia) -> str:
    """Reglas que sostienen el resultado, con identificador (para exportar y auditar)."""
    ids = [c.regla for c in res.candidatos if c.color == res.semaforo.value and not c.anulado]
    texto = ", ".join(f"{i} ({motor.por_id[i].nombre})" for i in ids)
    anuladas = [c.regla for c in res.candidatos if c.anulado]
    if anuladas:
        texto += f". Riesgo alto de {', '.join(anuladas)} anulado por la excepción R7"
    return texto


# ----------------------------------------------------------------------------- vista técnica
def que_hizo(regla_id: str, nuevos: dict) -> str:
    if "candidato" in nuevos:
        color = nuevos["candidato"].split(" ")[0]
        extra = " y descarta el riesgo alto" if "anula" in nuevos["candidato"] else ""
        return f"Propone {NIVEL[color].lower()}{extra}"
    if "prob_reprobar" in nuevos:
        return f"Probabilidad estimada: {pct(nuevos['prob_reprobar'])}"
    if "asistencia" in nuevos:
        return f"Asistencia considerada: {fmt('asistencia', nuevos['asistencia'])}"
    return ""


ESTADOS = {
    "sostiene": ":green[Se aplicó y sostiene el resultado]",
    "superada": ":orange[Se aplicó, pero otra regla indica un riesgo mayor]",
    "anulada": ":orange[Se aplicó, pero la excepción R7 la anuló]",
    "no_disparada": ":gray[No se aplicó]",
}


def arbol_markdown(arbol: dict) -> str:
    meta = NIVEL[arbol["meta"]].lower()
    if arbol["alcanzada"]:
        cab = f"Reglas que pueden concluir **{meta}** y cómo se evaluaron para este estudiante."
    else:
        cab = (f"El resultado fue **{NIVEL[arbol['semaforo_final']].lower()}**. "
               f"Estas son las reglas que podrían concluir **{meta}** y la condición que faltó.")
    out = [cab, ""]
    for n in arbol["reglas"]:
        out.append(f"**{n['id']}. {n['nombre']}**  \n{ESTADOS[n['estado']]}")
        out.append(f"> {n['texto']}")
        if n["conector"] == "O":
            out.append("> *(basta con una de las condiciones)*")
        for c in n["condiciones"]:
            marca = ":green[Cumple]" if c["cumple"] else ":red[No cumple]"
            out.append(f"- {marca}: {c['texto']}. Valor: **{fmt(c['hecho'], c['valor'])}**")
        out.append("")
    return "\n".join(out)
