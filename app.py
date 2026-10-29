"""Interfaz web del Sistema Experto de Alertas Tempranas en Ciencias Básicas.

Ejecutar localmente:   streamlit run app.py
Despliegue en la nube: ver README.md (Streamlit Community Cloud).
"""

from __future__ import annotations

import hashlib
import io
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from se_alertas.base_conocimiento import DESCRIPCION_UMBRALES, REGLAS, UMBRALES, texto_regla
from se_alertas.explicacion import ICONO, arbol_markdown, etiqueta, fmt, narrativa
from se_alertas.ingesta_simulada import LABS, FuenteMoodleSimulada, cargar_csv, plantilla_csv
from se_alertas.modelo_estadistico import ModeloRiesgo
from se_alertas.motor_inferencia import MotorInferencia, ResultadoInferencia
from se_alertas.ontologia import GLOSARIO, RELACIONES
from se_alertas.sistema import SistemaExperto, hechos_desde_fila

st.set_page_config(page_title="Alertas Tempranas · Sistema Experto", page_icon="🚦", layout="wide")

COLORES = {"ROJO": "#D64545", "AMARILLO": "#E0A100", "VERDE": "#2E9E5B"}
REGLAS_EDITABLES = [r.id for r in REGLAS if r.id not in ("P1", "M1")]

st.markdown(
    """
    <style>
      .badge {display:inline-block;padding:.35rem .9rem;border-radius:999px;font-weight:700;color:#fff;font-size:1.05rem}
      .tarjeta {border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:1rem 1.2rem;margin-bottom:.6rem}
      .tarjeta h4 {margin:0 0 .4rem 0}
      .muted {opacity:.7;font-size:.9rem}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------- datos y modelo
@st.cache_data(show_spinner=False)
def historico(semilla: int) -> pd.DataFrame:
    return FuenteMoodleSimulada(semilla=semilla).cohortes_historicas()


@st.cache_data(show_spinner=False)
def curso_actual(semilla: int, n: int) -> pd.DataFrame:
    return FuenteMoodleSimulada(semilla=semilla).curso_actual(n)


@st.cache_resource(show_spinner="Entrenando el modelo con cohortes anteriores…")
def modelo(semilla: int) -> ModeloRiesgo:
    return ModeloRiesgo.entrenar(historico(semilla), semilla)


def badge(color: str, texto: str | None = None) -> str:
    return f'<span class="badge" style="background:{COLORES[color]}">{ICONO[color]} {texto or color}</span>'


# ----------------------------------------------------------------------------- barra lateral
if "semilla" not in st.session_state:
    st.session_state.semilla = 2026

with st.sidebar:
    st.title("🚦 Alertas Tempranas")
    st.caption("Sistema experto · C++ y Estructuras de Datos · corte semana 3")

    fuente = st.radio("Fuente de datos", ["Moodle simulado", "Cargar CSV"], horizontal=True)
    if fuente == "Moodle simulado":
        n_est = st.slider("Estudiantes del semestre actual", 150, 300, 160, step=10)
        c1, c2 = st.columns([3, 2])
        c1.number_input("Semilla", min_value=1, max_value=99999, key="semilla",
                        help="Misma semilla = mismos datos. Útil para que todos vean lo mismo.")
        if c2.button("🎲 Nueva", width="stretch", help="Genera otro curso simulado"):
            st.session_state.semilla = int(time.time()) % 99999
            st.rerun()
        datos = curso_actual(st.session_state.semilla, n_est)
        firma_datos = f"sim-{st.session_state.semilla}-{n_est}"
    else:
        st.download_button("Descargar plantilla CSV", plantilla_csv(), "plantilla_estudiantes.csv", "text/csv",
                           width="stretch")
        archivo = st.file_uploader("CSV con el mismo formato", type="csv")
        if archivo is None:
            st.info("Cargue un CSV o vuelva a 'Moodle simulado'.")
            st.stop()
        try:
            contenido = archivo.getvalue()
            datos = cargar_csv(contenido)
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo leer el archivo: {e}")
            st.stop()
        n_est = len(datos)
        firma_datos = "csv-" + hashlib.md5(contenido).hexdigest()

    with st.expander("⚙️ Umbrales del experto"):
        st.caption("Valores elicitados en la entrevista. El docente puede ajustarlos.")
        if st.button("Restaurar valores de la entrevista", width="stretch"):
            for k in UMBRALES:
                st.session_state.pop(f"u_{k}", None)
        umbrales = {}
        for k, v in UMBRALES.items():
            paso = 0.1 if k.startswith(("nota", "moodle")) else 1.0
            maximo = 5.0 if k.startswith("nota") else (12.0 if k.startswith("moodle") else (30.0 if k.startswith("dias") else 100.0))
            umbrales[k] = st.slider(DESCRIPCION_UMBRALES[k], 0.0, maximo, float(v), paso, key=f"u_{k}")

    with st.expander("📏 Reglas activas"):
        st.caption("Desactive reglas para ver su efecto (auditoría cruzada).")
        activas = [rid for rid in REGLAS_EDITABLES if st.checkbox(rid, True, key=f"r_{rid}")]

    st.divider()
    st.caption("Prototipo académico · Sistemas Expertos (ISOFBL143) · UNIMINUTO 2026-2. "
               "**Todos los datos son ficticios** y se generan por simulación.")

semilla_modelo = st.session_state.semilla if fuente == "Moodle simulado" else 2026
mdl = modelo(semilla_modelo)
sistema = SistemaExperto(mdl, umbrales, activas)
motor: MotorInferencia = sistema.motor
firma = (firma_datos, tuple(sorted(umbrales.items())), tuple(activas))


# ----------------------------------------------------------------------------- componentes de UI
def detalle(res: ResultadoInferencia, nombre: str, clave: str) -> None:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(
            f"""<div class="tarjeta"><h4>{nombre}</h4>
            {badge(res.semaforo.value, f"{res.semaforo.value} · riesgo {res.semaforo.nivel_riesgo.lower()}")}
            <p style="margin:.8rem 0 .2rem 0"><b>Probabilidad de reprobar:</b> {res.probabilidad:.1f} %</p>
            <p style="margin:.2rem 0"><b>Certeza de la alerta:</b> {res.certeza}</p>
            <p style="margin:.2rem 0"><b>Regla decisiva:</b> {res.regla_decisiva}</p></div>""",
            unsafe_allow_html=True,
        )
        st.markdown("**Acciones sugeridas**")
        for a in res.acciones:
            st.markdown(f"- {a}")
    with c2:
        st.markdown("**Explicación**")
        st.markdown(narrativa(res, motor, nombre))

    t1, t2, t3, t4 = st.tabs(["❓ ¿Por qué? (hacia atrás)", "🔁 Traza (hacia adelante)",
                              "📊 Variables del modelo", "🗂️ Hechos"])
    with t1:
        opciones = ["ROJO", "AMARILLO", "VERDE"]
        meta = st.radio("Meta a explicar", opciones, index=opciones.index(res.semaforo.value), horizontal=True,
                        format_func=lambda c: f"¿Por qué {c}?" if c == res.semaforo.value else f"¿Por qué no {c}?",
                        key=f"meta_{clave}_{res.semaforo.value}")
        st.markdown(arbol_markdown(motor.encadenar_atras(res, meta)))
    with t2:
        st.caption("Cada fila es un ciclo reconocer → resolver conflicto → actuar. "
                   "La columna *Agenda* muestra el conjunto conflicto; se dispara la regla de mayor prioridad.")
        filas = [{
            "Ciclo": d.ciclo, "Regla disparada": d.regla, "Fase": d.fase,
            "Agenda (conjunto conflicto)": ", ".join(d.agenda),
            "Hechos usados": "; ".join(f"{etiqueta(k)} = {fmt(k, v)}" for k, v in d.hechos_usados.items()),
            "Hechos nuevos": "; ".join(f"{etiqueta(k)} = {fmt(k, v) if k != 'candidato' else v}"
                                       for k, v in d.hechos_nuevos.items()),
        } for d in res.traza]
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
        st.caption("Resolución final: gana el color más severo entre las conclusiones candidatas no anuladas "
                   "(principio de prudencia).")
    with t3:
        contrib = mdl.contribuciones(res.memoria).iloc[::-1]
        fig = go.Figure(go.Bar(
            x=contrib["aporte"], y=contrib["variable"], orientation="h",
            marker_color=["#D64545" if a > 0 else "#2E9E5B" for a in contrib["aporte"]],
            hovertemplate="%{y}: %{x:.2f}<extra></extra>",
        ))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                          title="Aporte de cada variable al riesgo (rojo sube, verde protege)",
                          xaxis_title="aporte al logit")
        st.plotly_chart(fig, width="stretch", key=f"contrib_{clave}")
    with t4:
        hechos = [{"Hecho": etiqueta(k), "Inicial": fmt(k, res.hechos_iniciales.get(k)) if k in res.hechos_iniciales else "—",
                   "Final (memoria de trabajo)": fmt(k, v)}
                  for k, v in res.memoria.items() if k not in ("sesiones_programadas", "sesiones_asistidas")]
        st.dataframe(pd.DataFrame(hechos), hide_index=True, width="stretch")


# ----------------------------------------------------------------------------- encabezado
st.title("Sistema Experto de Alertas Tempranas en Ciencias Básicas")
st.markdown(
    "Predice el **riesgo de reprobar** C++ y Estructuras de Datos antes de la **semana 4** y lo muestra en un "
    "**semáforo** con la justificación de cada alerta. Técnica híbrida: *modelo estadístico* entrenado con cohortes "
    "anteriores + *reglas SI…ENTONCES* del experto con encadenamiento hacia adelante."
)

tabs = st.tabs(["👥 Estudiantes", "🚦 Ejecutar y alertas", "🔍 Explicación", "🧪 Consulta individual",
                "📚 Base de conocimiento", "🏗️ Arquitectura"])

# ----------------------------------------------------------------------------- 1. Estudiantes
with tabs[0]:
    vista = datos.copy()
    vista["asistencia_%"] = (100 * vista["sesiones_asistidas"] / vista["sesiones_programadas"]).round(1)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Estudiantes", len(vista))
    m2.metric("Asistencia promedio", f"{vista['asistencia_%'].mean():.0f} %")
    m3.metric("Horas Moodle / semana (prom.)", f"{vista['horas_moodle_semana'].mean():.1f}")
    m4.metric("Con algún laboratorio sin entregar", int((vista["nota_lab1"].isna() | vista["nota_lab2"].isna()).sum()))
    cursos = st.multiselect("Filtrar por curso", sorted(vista["curso"].unique()), key="f_est_curso")
    if cursos:
        vista = vista[vista["curso"].isin(cursos)]
    st.dataframe(
        vista[["id", "nombre", "curso", "grupo", "asistencia_%", "sesiones_asistidas", "sesiones_programadas",
               "faltas_justificadas", "horas_moodle_semana", "dias_sin_ingreso_moodle", "nota_lab1", "nota_lab2",
               "puntaje_admision_mat", "repite_materia", "trabaja_tiempo_completo", "jornada", "tipo_colegio"]],
        hide_index=True, width="stretch", height=520,
        column_config={
            "id": "ID", "nombre": "Estudiante", "curso": "Curso", "grupo": "Grupo",
            "asistencia_%": st.column_config.NumberColumn("Asistencia %", format="%.1f"),
            "sesiones_asistidas": "Asistidas", "sesiones_programadas": "Programadas",
            "faltas_justificadas": "Faltas just.", "horas_moodle_semana": st.column_config.NumberColumn("Moodle h/sem", format="%.1f"),
            "dias_sin_ingreso_moodle": "Días sin ingreso",
            "nota_lab1": st.column_config.NumberColumn(f"Lab 1 · {LABS[1].split(' (')[0]}", format="%.1f"),
            "nota_lab2": st.column_config.NumberColumn(f"Lab 2 · {LABS[2]}", format="%.1f"),
            "puntaje_admision_mat": "Admisión mat.", "repite_materia": "Repite", "trabaja_tiempo_completo": "Trabaja",
            "jornada": "Jornada", "tipo_colegio": "Colegio",
        },
    )
    st.caption("Fuente: adaptador **Moodle simulado** (asistencia, conexión, laboratorios) + perfil de ingreso simulado. "
               "Notas vacías = laboratorio sin entregar. Nombres ficticios.")

# ----------------------------------------------------------------------------- 2. Ejecutar
with tabs[1]:
    c1, c2 = st.columns([1, 3])
    ejecutar = c1.button("▶ Ejecutar sistema experto", type="primary", width="stretch")
    c2.caption(f"Evalúa a los {len(datos)} estudiantes con {len(activas)} reglas activas y el modelo estadístico "
               f"(AUC {mdl.metricas['auc']:.2f}).")
    if ejecutar:
        t0 = time.perf_counter()
        tabla, resultados = sistema.evaluar_curso(datos)
        st.session_state.salida = {"tabla": tabla, "resultados": resultados, "firma": firma,
                                   "segundos": time.perf_counter() - t0}

    salida = st.session_state.get("salida")
    if not salida:
        st.info("Pulse **Ejecutar sistema experto** para generar el reporte de semaforización.")
    else:
        if salida["firma"] != firma:
            st.warning("Cambiaron los datos, los umbrales o las reglas activas. Vuelva a ejecutar para actualizar.")
        tabla = salida["tabla"]
        st.success(f"Inferencia completada en {salida['segundos']:.2f} s · {len(tabla)} estudiantes evaluados.")
        k = st.columns(3)
        for col, color in zip(k, ["ROJO", "AMARILLO", "VERDE"]):
            n = int((tabla["semaforo"] == color).sum())
            col.markdown(f'<div class="tarjeta">{badge(color)}<h2 style="margin:.4rem 0 0 0">{n}</h2>'
                         f'<span class="muted">{100 * n / len(tabla):.0f} % del curso</span></div>',
                         unsafe_allow_html=True)

        por_grupo = tabla.assign(g=tabla["curso"] + " " + tabla["grupo"]).groupby(["g", "semaforo"]).size().unstack(fill_value=0)
        fig = go.Figure()
        for color in ["ROJO", "AMARILLO", "VERDE"]:
            if color in por_grupo:
                fig.add_bar(name=color.title(), x=por_grupo.index, y=por_grupo[color], marker_color=COLORES[color])
        fig.update_layout(barmode="stack", height=300, margin=dict(l=10, r=10, t=30, b=10),
                          title="Semáforo por curso y grupo", legend_orientation="h", yaxis_title="estudiantes")
        st.plotly_chart(fig, width="stretch")

        f1, f2 = st.columns(2)
        sel_color = f1.multiselect("Semáforo", ["ROJO", "AMARILLO", "VERDE"], default=["ROJO", "AMARILLO", "VERDE"])
        sel_curso = f2.multiselect("Curso", sorted(tabla["curso"].unique()), key="f_alert_curso")
        vista = tabla[tabla["semaforo"].isin(sel_color)]
        if sel_curso:
            vista = vista[vista["curso"].isin(sel_curso)]
        vista = vista.assign(semaforo=vista["semaforo"].map(lambda c: f"{ICONO[c]} {c}"))
        st.dataframe(
            vista[["semaforo", "nombre", "curso", "grupo", "prob_reprobar", "asistencia", "horas_moodle", "nota_lab1",
                   "nota_lab2", "justificacion", "accion", "acciones_especificas", "certeza", "reglas_disparadas"]],
            hide_index=True, width="stretch", height=520,
            column_config={
                "semaforo": "Semáforo", "nombre": "Estudiante",
                "prob_reprobar": st.column_config.ProgressColumn("P(reprobar)", format="%.1f%%", min_value=0, max_value=100),
                "asistencia": st.column_config.NumberColumn("Asistencia %", format="%.0f"),
                "horas_moodle": st.column_config.NumberColumn("Moodle h/sem", format="%.1f"),
                "nota_lab1": st.column_config.NumberColumn("Lab 1", format="%.1f"),
                "nota_lab2": st.column_config.NumberColumn("Lab 2", format="%.1f"),
                "justificacion": st.column_config.TextColumn("Justificación (regla aplicada)", width="large"),
                "accion": "Acción", "acciones_especificas": "Acciones específicas",
                "certeza": "Certeza", "reglas_disparadas": "Reglas disparadas (orden)",
            },
        )
        st.caption("Ordenado por prioridad de atención: ROJO primero y, dentro de cada color, mayor probabilidad. "
                   "Vea el detalle de cualquier estudiante en la pestaña **Explicación**.")

        d1, d2, _ = st.columns([1, 1, 2])
        d1.download_button("⬇ Reporte CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                           "reporte_semaforo.csv", "text/csv", width="stretch")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            tabla.to_excel(xw, sheet_name="Semaforo", index=False)
        d2.download_button("⬇ Reporte Excel", buf.getvalue(), "reporte_semaforo.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")

# ----------------------------------------------------------------------------- 3. Explicación
with tabs[2]:
    salida = st.session_state.get("salida")
    if not salida:
        st.info("Primero ejecute el sistema experto en la pestaña **🚦 Ejecutar y alertas**.")
    else:
        tabla = salida["tabla"]
        etiquetas = {r.id: f"{ICONO[r.semaforo]} {r.nombre} — {r.prob_reprobar:.1f} % ({r.curso} {r.grupo})"
                     for r in tabla.itertuples()}
        sel = st.selectbox("Estudiante (ordenados por prioridad)", list(etiquetas), format_func=etiquetas.get)
        detalle(salida["resultados"][sel], tabla.set_index("id").loc[sel, "nombre"], f"curso_{sel}")

# ----------------------------------------------------------------------------- 4. Consulta individual
PRESETS = {
    "Caso 0 de la entrevista (60 % asistencia, 2 h Moodle, lab 1 = 1,8)":
        dict(prog=12, asist=7, just=0, horas=2.0, dias=6, e1=True, l1=1.8, e2=True, l2=2.2, adm=55, rep=False, trab=False),
    "Pregunta 4: asiste 90 % pero lab 1 = 1,5 (desbordamiento de memoria)":
        dict(prog=12, asist=11, just=0, horas=3.5, dias=2, e1=True, l1=1.5, e2=True, l2=3.4, adm=62, rep=False, trab=False),
    "Pregunta 4b: lo mismo, pero lab 2 también < 3,0":
        dict(prog=12, asist=11, just=0, horas=3.5, dias=2, e1=True, l1=1.5, e2=True, l2=2.4, adm=62, rep=False, trab=False),
    "Pregunta 5: asiste 50 %, mucho Moodle y buenas notas":
        dict(prog=12, asist=6, just=0, horas=5.5, dias=1, e1=True, l1=4.2, e2=True, l2=4.0, adm=70, rep=False, trab=True),
    "Pregunta 7: faltas justificadas (incapacidad)":
        dict(prog=12, asist=8, just=2, horas=3.0, dias=3, e1=True, l1=3.4, e2=True, l2=3.3, adm=60, rep=False, trab=False),
    "Pregunta 9: inactividad (12 días sin Moodle)":
        dict(prog=12, asist=10, just=0, horas=1.0, dias=12, e1=True, l1=3.6, e2=True, l2=3.2, adm=65, rep=False, trab=False),
    "Pregunta 9b: inactividad + lab 2 sin entregar (el modelo eleva a ROJO)":
        dict(prog=12, asist=10, just=0, horas=0.8, dias=12, e1=True, l1=3.6, e2=False, l2=0.0, adm=65, rep=False, trab=False),
    "Estudiante destacado": dict(prog=12, asist=12, just=0, horas=6.0, dias=0, e1=True, l1=4.6, e2=True, l2=4.5,
                                 adm=82, rep=False, trab=False),
}

with tabs[3]:
    st.markdown("Pruebe una **consulta básica** sobre el prototipo: ingrese los hechos de un estudiante hipotético "
                "(o use un caso de la entrevista al experto) y ejecute la inferencia.")
    preset = st.selectbox("Caso de partida", list(PRESETS))
    p = PRESETS[preset]
    kp = hashlib.md5(preset.encode()).hexdigest()[:6]
    with st.form("consulta"):
        a, b, c = st.columns(3)
        prog = a.number_input("Sesiones programadas", 1, 60, p["prog"], key=f"prog{kp}")
        asist = a.number_input("Sesiones asistidas", 0, 60, p["asist"], key=f"asist{kp}")
        just = a.number_input("Faltas justificadas", 0, 60, p["just"], key=f"just{kp}")
        horas = b.number_input("Horas en Moodle por semana", 0.0, 40.0, p["horas"], 0.5, key=f"horas{kp}")
        dias = b.number_input("Días sin ingresar a Moodle", 0, 60, p["dias"], key=f"dias{kp}")
        adm = b.number_input("Puntaje admisión matemáticas", 0, 100, p["adm"], key=f"adm{kp}")
        e1 = c.checkbox("Entregó laboratorio 1", p["e1"], key=f"e1{kp}")
        l1 = c.number_input("Nota laboratorio 1", 0.0, 5.0, p["l1"], 0.1, key=f"l1{kp}")
        e2 = c.checkbox("Entregó laboratorio 2", p["e2"], key=f"e2{kp}")
        l2 = c.number_input("Nota laboratorio 2", 0.0, 5.0, p["l2"], 0.1, key=f"l2{kp}")
        rep = c.checkbox("Repite la materia", p["rep"], key=f"rep{kp}")
        trab = c.checkbox("Trabaja tiempo completo", p["trab"], key=f"trab{kp}")
        consultar = st.form_submit_button("▶ Ejecutar consulta", type="primary")
    if asist + just > prog:
        st.error("Las sesiones asistidas más las faltas justificadas no pueden superar las programadas.")
    else:
        fila = dict(sesiones_programadas=prog, sesiones_asistidas=asist, faltas_justificadas=just,
                    horas_moodle_semana=horas, dias_sin_ingreso_moodle=dias,
                    nota_lab1=l1 if e1 else None, nota_lab2=l2 if e2 else None,
                    puntaje_admision_mat=adm, repite_materia=rep, trabaja_tiempo_completo=trab)
        detalle(motor.encadenar_adelante(hechos_desde_fila(fila)), "Estudiante de la consulta", f"consulta_{kp}")

# ----------------------------------------------------------------------------- 5. Base de conocimiento
with tabs[4]:
    st.subheader("Reglas de producción")
    st.caption("R0–R10: hoja *4_Reglas* de la entrevista al experto. P1, M1, R11 y R12 se agregaron al construir el "
               "prototipo (control del flujo y completitud).")
    st.table(pd.DataFrame([{
        "ID": r.id, "Regla (SI… ENTONCES…)": texto_regla(r, umbrales), "Fase": r.fase, "Prioridad": r.prioridad,
        "Certeza": r.certeza, "Origen": r.origen + (" · agregada" if r.agregada_en_prototipo else ""),
        "Activa": "Sí" if r.id in activas or r.id in ("P1", "M1") else "No",
    } for r in REGLAS]).set_index("ID"))
    st.markdown(
        "**Estrategia de control.** Encadenamiento hacia adelante por fases (Preparación → Modelo → Clasificación → "
        "Escalamiento → Completitud). Conflictos: prioridad, luego especificidad, luego orden. Refracción: cada regla "
        "se dispara una vez por estudiante. Resolución del color: el más severo (prudencia); R7 es una **excepción** "
        "que anula los ROJO de R0/R1/R2 para evitar falsos positivos. El encadenamiento hacia atrás se usa solo en el "
        "módulo de explicación."
    )

    st.subheader("Modelo estadístico (cohortes anteriores)")
    met = mdl.metricas
    c = st.columns(4)
    c[0].metric("Cohortes históricas", f"{met['n_entrenamiento'] + met['n_prueba']:,} est.".replace(",", "."))
    c[1].metric("AUC (prueba)", f"{met['auc']:.2f}")
    c[2].metric("Exactitud (umbral 50 %)", f"{100 * met['exactitud']:.0f} %")
    c[3].metric("Tasa histórica de reprobación", f"{100 * met['tasa_reprobacion_historica']:.0f} %")
    coef = mdl.coeficientes().iloc[::-1]
    fig = go.Figure(go.Bar(x=coef.iloc[:, 1], y=coef["variable"], orientation="h",
                           marker_color=["#D64545" if v > 0 else "#2E9E5B" for v in coef.iloc[:, 1]]))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10),
                      title="Coeficientes de la regresión logística (estandarizados)")
    st.plotly_chart(fig, width="stretch")
    with st.expander("Ver datos históricos simulados (2023-1 a 2025-2)"):
        st.dataframe(historico(semilla_modelo), hide_index=True, width="stretch")

    st.subheader("Ontología del dominio")
    o1, o2 = st.columns(2)
    o1.dataframe(pd.DataFrame(RELACIONES, columns=["Entidad origen", "Relación", "Entidad destino"]), hide_index=True,
                 width="stretch")
    o2.table(pd.DataFrame(list(GLOSARIO.items()), columns=["Concepto", "Definición"]).set_index("Concepto"))
    st.caption("Taxonomía de riesgo: ALTO = 🔴 ROJO · MEDIO = 🟡 AMARILLO · BAJO = 🟢 VERDE.")

# ----------------------------------------------------------------------------- 6. Arquitectura
with tabs[5]:
    st.graphviz_chart(
        """
        digraph G {
          rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.45;
          node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12, margin="0.18,0.08"];
          edge [fontname="Helvetica", fontsize=10, color="#888888", fontcolor="#666666"];
          subgraph cluster_fuentes { label="Fuentes de datos (100 % SIMULADAS)"; style="dashed"; color="#999999";
            fontname="Helvetica"; fontsize=11;
            moodle [label="Moodle simulado\\nasistencia · conexión · laboratorios", fillcolor="#E8EEF9"];
            notas  [label="Sistema de notas + perfil de ingreso\\n(mock)", fillcolor="#E8EEF9"];
            hist   [label="Cohortes 2023-1 … 2025-2\\n1.200 estudiantes con resultado final", fillcolor="#E8EEF9"]; }
          ingesta [label="Adaptador de ingesta\\ningesta_simulada.py", fillcolor="#DDE7F7"];
          hechos  [label="Base de hechos\\n(memoria de trabajo)", fillcolor="#FFF4D6"];
          reglas  [label="Base de reglas\\nP1 · R0–R12 · M1\\n(umbrales editables)", fillcolor="#FFF4D6"];
          modelo  [label="Modelo estadístico\\nregresión logística", fillcolor="#FCE3E3"];
          motor   [label="MOTOR DE INFERENCIA\\nencadenamiento hacia adelante\\nagenda · prioridad · refracción", fillcolor="#E3F4EA", penwidth=2];
          expl    [label="Módulo de explicación\\nencadenamiento hacia atrás\\n¿por qué? / ¿por qué no?", fillcolor="#E3F4EA"];
          ui      [label="Interfaz web (Streamlit Cloud)\\ntablero docente · semáforo · exportación", fillcolor="#EDE7F6"];
          docente [label="Docente", shape=ellipse, fillcolor="#FFFFFF"];
          moodle -> ingesta; notas -> ingesta;
          hist -> modelo [label=" entrena"];
          ingesta -> hechos [label=" hechos iniciales"];
          {rank=same; hechos; reglas; modelo}
          hechos -> motor; reglas -> motor;
          motor -> modelo [label=" M1 invoca", style=dashed]; modelo -> motor [label=" P(reprobar)"];
          motor -> hechos [label=" hechos derivados", style=dashed];
          motor -> expl [label=" traza"]; reglas -> expl;
          motor -> ui [label=" alertas"]; expl -> ui [label=" justificación"];
          ui -> docente [dir=both, label=" consulta · ajusta umbrales"];
        }
        """,
        width="stretch",
    )
    st.markdown(
        """
| Componente | Responsabilidad | Archivo |
|---|---|---|
| Adaptador de ingesta (simulado) | Genera estudiantes ficticios, asistencia, Moodle, laboratorios y cohortes históricas; también acepta CSV | `se_alertas/ingesta_simulada.py` |
| Ontología | Entidades, relaciones, taxonomía de riesgo y glosario | `se_alertas/ontologia.py` |
| Base de conocimiento | Reglas declarativas SI…ENTONCES con certeza, origen y prioridad; umbrales editables | `se_alertas/base_conocimiento.py` |
| Modelo estadístico | Regresión logística entrenada con cohortes anteriores; aporte por variable | `se_alertas/modelo_estadistico.py` |
| Motor de inferencia | Encadenamiento hacia adelante (alerta) y hacia atrás (explicación) | `se_alertas/motor_inferencia.py` |
| Módulo de explicación | Narrativa, ¿por qué?, ¿por qué no?, traza | `se_alertas/explicacion.py` |
| Fachada | Orquesta el flujo completo por estudiante y por curso | `se_alertas/sistema.py` |
| Interfaz | Tablero web desplegado en Streamlit Community Cloud | `app.py` |
"""
    )
