"""Motor de inferencia.

* Encadenamiento HACIA ADELANTE (dirigido por datos) para producir la alerta:
  ciclo  reconocer -> resolver conflicto -> actuar  hasta que la agenda queda vacía.
    - Memoria de trabajo: diccionario de hechos del estudiante.
    - Agenda (conjunto conflicto): reglas activas cuyas condiciones se cumplen y que aún no
      se han disparado (refracción: cada regla se dispara a lo sumo una vez por estudiante).
    - Resolución de conflictos: 1) prioridad (salience) 2) especificidad (n.º de condiciones)
      3) orden en la base de reglas.
    - El modelo estadístico se invoca como procedimiento adjunto desde la regla M1.
    - El semáforo final es la conclusión candidata MÁS SEVERA (principio de prudencia),
      salvo que una regla de excepción (R7) anule los ROJO por asistencia/probabilidad.

* Encadenamiento HACIA ATRÁS (dirigido por metas) solo para explicar:
  meta "semáforo = X"  ->  ¿qué reglas concluyen X?  ->  ¿se cumplían sus condiciones?
  -> si una condición usa un hecho derivado, se vuelve a preguntar quién lo produjo.
  Así responde "¿por qué ROJO?" y también "¿por qué no VERDE?".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .base_conocimiento import (
    PRODUCTORES,
    REGLAS,
    UMBRALES,
    Condicion,
    Regla,
    resolver,
    texto_condicion,
    texto_regla,
)
from .ontologia import Semaforo


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


@dataclass
class Candidato:
    color: str
    regla: str
    veta_rojo: bool = False
    anulado: bool = False


@dataclass
class Disparo:
    ciclo: int
    regla: str
    fase: str
    agenda: list[str]
    hechos_usados: dict
    hechos_nuevos: dict
    texto: str


@dataclass
class ResultadoInferencia:
    hechos_iniciales: dict
    memoria: dict
    traza: list[Disparo]
    candidatos: list[Candidato]
    semaforo: Semaforo
    probabilidad: float
    reglas_disparadas: list[str]
    acciones: list[str]
    certeza: str

    @property
    def regla_decisiva(self) -> Optional[str]:
        """Primera regla (por orden de disparo) que concluyó el color final y no fue anulada."""
        for c in self.candidatos:
            if c.color == self.semaforo.value and not c.anulado:
                return c.regla
        return None


class MotorInferencia:
    def __init__(self, modelo, umbrales: Optional[dict] = None, reglas_activas: Optional[Iterable[str]] = None,
                 reglas: tuple[Regla, ...] = REGLAS):
        self.modelo = modelo
        self.umbrales = {**UMBRALES, **(umbrales or {})}
        activas = set(reglas_activas) if reglas_activas is not None else {r.id for r in reglas}
        # P1 y M1 controlan el flujo: siempre activas
        self.reglas = [r for r in reglas if r.id in activas or r.id in ("P1", "M1")]
        self.por_id = {r.id: r for r in reglas}

    # ------------------------------------------------------------------ evaluación
    def evaluar(self, c: Condicion, mem: dict) -> tuple[bool, Any]:
        obs = mem.get(c.hecho)
        if c.op == "existe":
            return (c.hecho in mem and not _vacio(obs)), obs
        if _vacio(obs):
            return False, obs  # sin dato (p. ej. laboratorio sin entregar) la comparación no se cumple
        v = resolver(c.valor, self.umbrales)
        ops = {
            "<": lambda: obs < v,
            "<=": lambda: obs <= v,
            ">": lambda: obs > v,
            ">=": lambda: obs >= v,
            "==": lambda: obs == v,
            "entre": lambda: v[0] <= obs < v[1],
        }
        return bool(ops[c.op]()), obs

    def cumple(self, r: Regla, mem: dict) -> bool:
        resultados = [self.evaluar(c, mem)[0] for c in r.condiciones]
        return any(resultados) if r.conector == "O" else all(resultados)

    def _actualizar_derivados(self, mem: dict, candidatos: list[Candidato]) -> None:
        veto = any(c.veta_rojo for c in candidatos)
        for c in candidatos:
            c.anulado = veto and c.color == "ROJO" and self.por_id[c.regla].veta_por_excepcion
        validos = [Semaforo(c.color) for c in candidatos if not c.anulado]
        mem["n_candidatos"] = len(candidatos)
        mem["semaforo_provisional"] = max(validos, key=lambda s: s.severidad).value if validos else None

    # ------------------------------------------------------------------ hacia adelante
    def encadenar_adelante(self, hechos: dict) -> ResultadoInferencia:
        mem = dict(hechos)
        candidatos: list[Candidato] = []
        disparadas: set[str] = set()
        traza: list[Disparo] = []
        self._actualizar_derivados(mem, candidatos)

        orden = {r.id: i for i, r in enumerate(self.reglas)}
        ciclo = 0
        while True:
            agenda = [r for r in self.reglas if r.id not in disparadas and self.cumple(r, mem)]
            if not agenda:
                break
            agenda.sort(key=lambda r: (-r.prioridad, -len(r.condiciones), orden[r.id]))
            regla = agenda[0]
            ciclo += 1
            usados = {c.hecho: mem.get(c.hecho) for c in regla.condiciones}
            nuevos = self._actuar(regla, mem, candidatos)
            disparadas.add(regla.id)
            self._actualizar_derivados(mem, candidatos)
            traza.append(Disparo(ciclo, regla.id, regla.fase, [r.id for r in agenda], usados, nuevos,
                                 texto_regla(regla, self.umbrales)))

        semaforo = Semaforo(mem["semaforo_provisional"] or "VERDE")
        efectivas = [c.regla for c in candidatos if c.color == semaforo.value and not c.anulado]
        certezas = [self.por_id[r].certeza for r in efectivas]
        acciones = [semaforo.accion_base]
        for d in traza:
            r = self.por_id[d.regla]
            cand = next((c for c in candidatos if c.regla == r.id), None)
            if r.accion and cand and not cand.anulado and r.accion not in acciones:
                # evita repetir la acción base (p. ej. "tutoría individual" ya incluida por el color ROJO)
                if "tutoría individual" in r.accion.lower() and "tutoría individual" in semaforo.accion_base.lower():
                    continue
                if r.accion.lower().startswith("seguimiento") and semaforo.accion_base.lower().startswith("seguimiento"):
                    continue
                acciones.append(r.accion)
        return ResultadoInferencia(
            hechos_iniciales=dict(hechos),
            memoria=mem,
            traza=traza,
            candidatos=candidatos,
            semaforo=semaforo,
            probabilidad=float(mem.get("prob_reprobar", float("nan"))),
            reglas_disparadas=[d.regla for d in traza],
            acciones=acciones,
            certeza="Alta" if "Alta" in certezas else ("Media" if certezas else "Baja"),
        )

    def _actuar(self, r: Regla, mem: dict, candidatos: list[Candidato]) -> dict:
        concl = r.conclusion
        if concl.tipo == "asignar":
            valor = mem.get(concl.valor[1:]) if isinstance(concl.valor, str) and concl.valor.startswith("$") else concl.valor
            mem[concl.hecho] = valor
            return {concl.hecho: valor}
        if concl.tipo == "recalcular_asistencia":
            efectivas = max(mem["sesiones_programadas"] - mem["faltas_justificadas"], 1)
            valor = round(100.0 * mem["sesiones_asistidas"] / efectivas, 1)
            mem["asistencia"] = valor
            return {"asistencia": valor}
        if concl.tipo == "modelo":
            valor = self.modelo.probabilidad(mem)
            mem["prob_reprobar"] = valor
            return {"prob_reprobar": valor}
        if concl.tipo == "candidato":
            candidatos.append(Candidato(concl.valor, r.id, concl.veta_rojo))
            return {"candidato": concl.valor + (" (anula ROJO)" if concl.veta_rojo else "")}
        raise ValueError(f"Tipo de conclusión desconocido: {concl.tipo}")

    # ------------------------------------------------------------------ hacia atrás
    def encadenar_atras(self, res: ResultadoInferencia, meta: str, profundidad: int = 0) -> dict:
        """Árbol de explicación para la meta 'semáforo = meta'."""
        disparos = {d.regla: d for d in res.traza}
        cand = {c.regla: c for c in res.candidatos}
        nodos = []
        for r in self.reglas:
            if r.conclusion.tipo != "candidato" or r.conclusion.valor != meta:
                continue
            nodos.append(self._nodo_regla(r, res, disparos, cand))
        # Primero las reglas que sostienen la meta
        nodos.sort(key=lambda n: {"sostiene": 0, "anulada": 1, "superada": 2, "no_disparada": 3}[n["estado"]])
        return {
            "meta": meta,
            "alcanzada": res.semaforo.value == meta,
            "semaforo_final": res.semaforo.value,
            "reglas": nodos,
        }

    def _nodo_regla(self, r: Regla, res: ResultadoInferencia, disparos: dict, cand: dict) -> dict:
        disparo = disparos.get(r.id)
        mem = disparo.hechos_usados if disparo else res.memoria
        conds = []
        for c in r.condiciones:
            ok, obs = self.evaluar(c, {**res.memoria, **mem})
            sub = self._explicar_hecho(c.hecho, res, disparos) if c.hecho in PRODUCTORES else None
            conds.append({"texto": texto_condicion(c, self.umbrales), "hecho": c.hecho, "valor": obs,
                          "cumple": ok, "sub": sub})
        if disparo:
            ca = cand.get(r.id)
            if ca and ca.anulado:
                estado = "anulada"
            elif r.conclusion.valor == res.semaforo.value:
                estado = "sostiene"
            else:
                estado = "superada"
        else:
            estado = "no_disparada"
        return {
            "id": r.id, "nombre": r.nombre, "texto": texto_regla(r, self.umbrales), "conector": r.conector,
            "estado": estado, "certeza": r.certeza, "origen": r.origen,
            "ciclo": disparo.ciclo if disparo else None, "condiciones": conds,
        }

    def _explicar_hecho(self, hecho: str, res: ResultadoInferencia, disparos: dict) -> Optional[dict]:
        for rid in PRODUCTORES[hecho]:
            if rid in disparos:
                d = disparos[rid]
                return {"regla": rid, "texto": d.texto, "valor": d.hechos_nuevos.get(hecho), "ciclo": d.ciclo}
        return None
