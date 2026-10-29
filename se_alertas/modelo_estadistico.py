"""Modelo estadístico (técnica principal del Excel: "Modelos matemáticos y estadísticos
entrenados con cohortes anteriores").

Regresión logística (scikit-learn) entrenada con las cohortes históricas simuladas.
Se eligió la regresión logística porque:
  1. Su salida es directamente una probabilidad (0–100 %), que es lo que piden el caso y el Excel.
  2. Es interpretable: cada coeficiente dice cuánto sube o baja el riesgo una variable,
     lo que alimenta el módulo de explicación ("qué variables pesaron más").

El motor de inferencia invoca este modelo como un "procedimiento adjunto" (regla M1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

VARIABLES = [
    ("asistencia", "Asistencia (%)"),
    ("horas_moodle_semana", "Horas en Moodle / semana"),
    ("dias_sin_ingreso_moodle", "Días sin ingresar a Moodle"),
    ("nota_lab1", "Nota laboratorio 1"),
    ("nota_lab2", "Nota laboratorio 2"),
    ("puntaje_admision_mat", "Puntaje admisión (matemáticas)"),
    ("repite_materia", "Repite la materia"),
    ("trabaja_tiempo_completo", "Trabaja tiempo completo"),
]
NOMBRES = dict(VARIABLES)


def asistencia_ajustada(asistidas: float, programadas: float, justificadas: float, umbral: float = 70.0) -> float:
    """Misma lógica que la regla R8 (para entrenar el modelo con la variable que verá en producción)."""
    bruta = 100.0 * asistidas / max(programadas, 1)
    if justificadas > 0 and bruta < umbral:
        return round(100.0 * asistidas / max(programadas - justificadas, 1), 1)
    return round(bruta, 1)


def vector(hechos: dict) -> np.ndarray:
    """Convierte hechos de la memoria de trabajo en el vector de entrada del modelo.
    Un laboratorio sin entregar entra al modelo con nota 0,0 (así lo califica la institución)."""
    def nota(v):
        return 0.0 if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)

    return np.array(
        [
            float(hechos["asistencia"]),
            float(hechos["horas_moodle_semana"]),
            float(hechos["dias_sin_ingreso_moodle"]),
            nota(hechos.get("nota_lab1")),
            nota(hechos.get("nota_lab2")),
            float(hechos["puntaje_admision_mat"]),
            float(bool(hechos["repite_materia"])),
            float(bool(hechos["trabaja_tiempo_completo"])),
        ]
    )


def _matriz(df: pd.DataFrame) -> np.ndarray:
    filas = []
    for r in df.to_dict("records"):
        r = dict(r)
        r["asistencia"] = asistencia_ajustada(r["sesiones_asistidas"], r["sesiones_programadas"], r["faltas_justificadas"])
        filas.append(vector(r))
    return np.vstack(filas)


@dataclass
class ModeloRiesgo:
    pipeline: Pipeline
    metricas: dict

    @classmethod
    def entrenar(cls, historico: pd.DataFrame, semilla: int = 2026) -> "ModeloRiesgo":
        X = _matriz(historico)
        y = historico["reprobo"].to_numpy()
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=semilla, stratify=y)
        pipe = Pipeline([("escala", StandardScaler()), ("logit", LogisticRegression(max_iter=1000))])
        pipe.fit(X_tr, y_tr)
        p = pipe.predict_proba(X_te)[:, 1]
        metricas = {
            "n_entrenamiento": int(len(y_tr)),
            "n_prueba": int(len(y_te)),
            "tasa_reprobacion_historica": float(y.mean()),
            "auc": float(roc_auc_score(y_te, p)),
            "exactitud": float(accuracy_score(y_te, p >= 0.5)),
            "brier": float(brier_score_loss(y_te, p)),
        }
        return cls(pipe, metricas)

    def probabilidad(self, hechos: dict) -> float:
        """Probabilidad de reprobar en porcentaje (0–100)."""
        p = self.pipeline.predict_proba(vector(hechos).reshape(1, -1))[0, 1]
        return round(100.0 * float(p), 1)

    def contribuciones(self, hechos: dict) -> pd.DataFrame:
        """Aporte de cada variable al logit (coef × valor estandarizado).
        Positivo = empuja hacia reprobar; negativo = protege."""
        esc: StandardScaler = self.pipeline.named_steps["escala"]
        logit: LogisticRegression = self.pipeline.named_steps["logit"]
        x = vector(hechos)
        z = (x - esc.mean_) / esc.scale_
        aporte = logit.coef_[0] * z
        return (
            pd.DataFrame(
                {"variable": [n for _, n in VARIABLES], "valor": x, "aporte": aporte}
            )
            .assign(abs=lambda d: d["aporte"].abs())
            .sort_values("abs", ascending=False)
            .drop(columns="abs")
            .reset_index(drop=True)
        )

    def coeficientes(self) -> pd.DataFrame:
        logit: LogisticRegression = self.pipeline.named_steps["logit"]
        return (
            pd.DataFrame({"variable": [n for _, n in VARIABLES], "coeficiente (estandarizado)": logit.coef_[0]})
            .sort_values("coeficiente (estandarizado)", key=abs, ascending=False)
            .reset_index(drop=True)
        )
