"""Módulo de explicación: convierte la traza y el árbol de encadenamiento hacia atrás
en textos que el docente entiende (ej.: "ROJO porque asistencia 55 % y laboratorio 1 = 1,8")."""

from __future__ import annotations

import math
from typing import Any

from .base_conocimiento import ETIQUETAS_HECHOS
from .motor_inferencia import MotorInferencia, ResultadoInferencia

CORTAS = {
    "asistencia": "asistencia",
    "asistencia_bruta": "asistencia registrada",
    "nota_lab1": "lab 1",
    "nota_lab2": "lab 2",
    "horas_moodle_semana": "Moodle",
    "dias_sin_ingreso_moodle": "sin ingresar",
    "labs_sin_entregar": "labs sin entregar",
    "prob_reprobar": "P(reprobar)",
    "repite_materia": "repite",
    "faltas_justificadas": "faltas justificadas",
    "semaforo_provisional": "semáforo previo",
    "n_candidatos": "otras conclusiones",
}

ICONO = {"ROJO": "🔴", "AMARILLO": "🟡", "VERDE": "🟢"}


def fmt(hecho: str, v: Any) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "sin entregar" if hecho.startswith("nota_lab") else "sin dato"
    if hecho == "prob_reprobar":
        return f"{v:.1f} %".replace(".", ",")
    if hecho in ("asistencia", "asistencia_bruta"):
        return f"{v:.0f} %"
    if hecho.startswith("nota_lab"):
        return f"{v:.1f}".replace(".", ",")
    if hecho == "horas_moodle_semana":
        return f"{v:.1f} h/sem".replace(".", ",")
    if hecho == "dias_sin_ingreso_moodle":
        return f"{int(v)} días"
    if isinstance(v, bool):
        return "sí" if v else "no"
    return str(v)


def resumen_corto(res: ResultadoInferencia, motor: MotorInferencia) -> str:
    color = res.semaforo.value
    partes = []
    for c in res.candidatos:
        if c.color != color or c.anulado:
            continue
        regla = motor.por_id[c.regla]
        disparo = next(d for d in res.traza if d.regla == c.regla)
        datos = []
        for cond in regla.condiciones:
            if cond.hecho in ("n_candidatos",):
                continue
            ok, _ = motor.evaluar(cond, {**res.memoria, **disparo.hechos_usados})
            if regla.conector == "O" and not ok:
                continue
            datos.append(f"{CORTAS.get(cond.hecho, cond.hecho)} {fmt(cond.hecho, disparo.hechos_usados.get(cond.hecho))}")
        partes.append(f"{c.regla} ({', '.join(datos)})")
    anuladas = [c.regla for c in res.candidatos if c.anulado]
    texto = f"{color} por " + " + ".join(partes) if partes else f"{color} (sin regla de soporte)"
    if anuladas:
        texto += f" · ROJO de {', '.join(anuladas)} anulado por excepción R7"
    return texto


def narrativa(res: ResultadoInferencia, motor: MotorInferencia, nombre: str = "El estudiante") -> str:
    m = res.memoria
    lineas = [
        f"{nombre} queda en **{ICONO[res.semaforo.value]} {res.semaforo.value}** (riesgo {res.semaforo.nivel_riesgo.lower()}) "
        f"con una probabilidad estimada de reprobar de **{fmt('prob_reprobar', res.probabilidad)}**.",
    ]
    if "R8" in res.reglas_disparadas:
        lineas.append(
            f"Antes de evaluar, la regla R8 descontó {m['faltas_justificadas']} falta(s) justificada(s): la asistencia pasó de "
            f"{fmt('asistencia', m['asistencia_bruta'])} a {fmt('asistencia', m['asistencia'])}."
        )
    lineas.append(f"Motivo: {resumen_corto(res, motor)}.")
    superadas = [c for c in res.candidatos if c.color != res.semaforo.value and not c.anulado]
    if superadas:
        lineas.append(
            "Otras conclusiones candidatas ("
            + ", ".join(f"{c.regla}→{c.color}" for c in superadas)
            + ") quedaron superadas por el principio de prudencia: gana el color más severo."
        )
    lineas.append("Acciones sugeridas: " + "; ".join(res.acciones) + ".")
    return "\n\n".join(lineas)


ESTADOS = {
    "sostiene": ("✅", "Disparada — sostiene la conclusión"),
    "superada": ("↗️", "Disparada — superada por un color más severo"),
    "anulada": ("⛔", "Disparada — anulada por la excepción R7"),
    "no_disparada": ("✖️", "No disparada"),
}


def arbol_markdown(arbol: dict) -> str:
    meta = arbol["meta"]
    if arbol["alcanzada"]:
        cab = f"**¿Por qué {ICONO[meta]} {meta}?** Meta alcanzada. Reglas que concluyen {meta}:"
    else:
        cab = (f"**¿Por qué no {ICONO[meta]} {meta}?** El semáforo final es {ICONO[arbol['semaforo_final']]} "
               f"{arbol['semaforo_final']}. Reglas que podrían concluir {meta} y por qué no lo lograron:")
    out = [cab, ""]
    for n in arbol["reglas"]:
        ic, est = ESTADOS[n["estado"]]
        ciclo = f" · ciclo {n['ciclo']}" if n["ciclo"] else ""
        out.append(f"{ic} **{n['id']} — {n['nombre']}** · {est}{ciclo} · certeza {n['certeza']} · origen: {n['origen']}")
        out.append(f"   - *{n['texto']}*")
        if n["conector"] == "O":
            out.append("   - (basta con que se cumpla una condición)")
        for c in n["condiciones"]:
            marca = "✔" if c["cumple"] else "✘"
            out.append(f"   - {marca} {c['texto']} → observado: **{fmt(c['hecho'], c['valor'])}**")
            if c["sub"]:
                s = c["sub"]
                out.append(f"      - ↳ dato derivado por **{s['regla']}** (ciclo {s['ciclo']}): {s['texto']}")
        out.append("")
    return "\n".join(out)


def etiqueta(hecho: str) -> str:
    return ETIQUETAS_HECHOS.get(hecho, hecho)
