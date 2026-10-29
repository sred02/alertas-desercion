"""Interfaz web del Sistema Experto de Alertas Tempranas en Ciencias Básicas.

Ejecutar localmente:   streamlit run app.py
Despliegue en la nube: ver README.md (Streamlit Community Cloud).
"""

from __future__ import annotations

import hashlib
import html
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from se_alertas.base_conocimiento import DESCRIPCION_UMBRALES, REGLAS, UMBRALES, texto_regla
from se_alertas.explicacion import (
    NIVEL, ajustes, arbol_markdown, fmt, motivos, pct, que_hizo, senales_adicionales,
)
from se_alertas.ingesta_simulada import FuenteMoodleSimulada, cargar_csv, plantilla_csv
from se_alertas.modelo_estadistico import ModeloRiesgo
from se_alertas.motor_inferencia import MotorInferencia, ResultadoInferencia
from se_alertas.ontologia import GLOSARIO, RELACIONES
from se_alertas.sistema import SistemaExperto, hechos_desde_fila

st.set_page_config(page_title="Alertas tempranas", layout="wide")

SEMILLA = 2026  # datos simulados fijos: todos los evaluadores ven el mismo curso
COLOR = {"ROJO": "#B4443A", "AMARILLO": "#B98512", "VERDE": "#3D7A58"}
TINTE = {"ROJO": "#F5E1DE", "AMARILLO": "#F6ECD2", "VERDE": "#E1EEE5"}
PRIMARIO, TINTA, LINEA = "#2B5D7A", "#1E2A32", "#DCE1DD"
REGLAS_EDITABLES = [r for r in REGLAS if r.id not in ("P1", "M1")]

st.markdown(
    f"""
    <style>
      .block-container {{max-width: 1180px; padding-top: 2.2rem;}}
      h1, h2, h3, h4 {{letter-spacing: -0.01em;}}
      .encabezado h1 {{font-size: 1.9rem; font-weight: 600; margin: 0;}}
      .encabezado p {{color: #5B6770; margin: .15rem 0 0 0;}}
      .pill {{display:inline-block; padding:.18rem .6rem; border-radius:4px; font-weight:600; font-size:.88rem;}}
      .resumen {{display:grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; margin: .4rem 0 .7rem 0;}}
      .resumen .n {{font-size: 2.1rem; font-weight: 600; line-height: 1.1; font-variant-numeric: tabular-nums;}}
      .resumen .t {{color:#5B6770; font-size:.92rem;}}
      .resumen .marca {{display:inline-block; width:.7rem; height:.7rem; border-radius:2px; margin-right:.45rem;}}
      .franja {{display:flex; height:12px; border-radius:6px; overflow:hidden; margin-bottom:1.6rem;}}
      .ficha {{background:#FFFFFF; border:1px solid {LINEA}; border-left-width:5px; border-radius:6px;
              padding:1.1rem 1.3rem; margin:.4rem 0 1rem 0; display:flex; justify-content:space-between;
              align-items:center; gap:1rem; flex-wrap:wrap;}}
      .ficha h3 {{margin:0 0 .15rem 0; font-size:1.35rem; font-weight:600;}}
      .ficha .sub {{color:#5B6770; font-size:.95rem;}}
      .ficha .prob {{text-align:right;}}
      .ficha .prob .n {{font-size:2.2rem; font-weight:600; line-height:1; font-variant-numeric: tabular-nums;}}
      .ficha .prob .t {{color:#5B6770; font-size:.85rem;}}
      .indicadores {{display:grid; grid-template-columns: repeat(4, 1fr); border-top:1px solid {LINEA};
                     border-bottom:1px solid {LINEA}; margin: .8rem 0 1rem 0;}}
      .indicadores div {{padding:.7rem .2rem;}}
      .indicadores .t {{color:#5B6770; font-size:.85rem;}}
      .indicadores .v {{font-size:1.2rem; font-weight:600; font-variant-numeric: tabular-nums;}}
      .vacio {{background:#FFFFFF; border:1px dashed #B9C2BC; border-radius:6px; padding:2rem; text-align:center;
               color:#4A5660; margin: 1rem 0;}}
      .muted {{color:#5B6770; font-size:.92rem;}}
      @media (max-width: 700px) {{
        .resumen, .indicadores {{grid-template-columns: repeat(2, 1fr);}}
        .ficha .prob {{text-align:left;}}
      }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------- datos y modelo
@st.cache_data(show_spinner=False)
def historico() -> pd.DataFrame:
    return FuenteMoodleSimulada(semilla=SEMILLA).cohortes_historicas()


@st.cache_data(show_spinner=False)
def curso_actual(n: int) -> pd.DataFrame:
    return FuenteMoodleSimulada(semilla=SEMILLA).curso_actual(n)


@st.cache_resource(show_spinner="Preparando el modelo con los semestres anteriores…")
def modelo() -> ModeloRiesgo:
    return ModeloRiesgo.entrenar(historico(), SEMILLA)


def pill(color: str) -> str:
    return (f'<span class="pill" style="background:{TINTE[color]};color:{COLOR[color]}">'
            f'{NIVEL[color]}</span>')


# ----------------------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown("### Configuración")

    fuente = st.radio("Origen de los datos", ["Simulados (Moodle)", "Archivo CSV"],
                      help="Los datos simulados reemplazan la conexión a Moodle y al sistema de notas.")
    if fuente == "Simulados (Moodle)":
        n_est = st.slider("Cantidad de estudiantes", 150, 300, 160, step=10)
        datos = curso_actual(n_est)
        firma_datos = f"sim-{n_est}"
    else:
        archivo = st.file_uploader("Archivo CSV", type="csv", help="Debe tener las mismas columnas que la plantilla.")
        st.download_button("Descargar plantilla", plantilla_csv(), "plantilla_estudiantes.csv", "text/csv",
                           width="stretch")
        if archivo is None:
            st.info("Sube un archivo CSV para continuar, o vuelve a los datos simulados.")
            st.stop()
        try:
            contenido = archivo.getvalue()
            datos = cargar_csv(contenido)
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo leer el archivo. {e}")
            st.stop()
        firma_datos = "csv-" + hashlib.md5(contenido).hexdigest()

    with st.expander("Umbrales del experto"):
        st.caption("Valores definidos en la entrevista al docente.")
        if st.button("Restablecer valores", width="stretch"):
            for k in UMBRALES:
                st.session_state.pop(f"u_{k}", None)
        umbrales = {}
        for k, v in UMBRALES.items():
            paso = 0.1 if k.startswith(("nota", "moodle")) else 1.0
            maximo = 5.0 if k.startswith("nota") else (12.0 if k.startswith("moodle") else (30.0 if k.startswith("dias") else 100.0))
            umbrales[k] = st.slider(DESCRIPCION_UMBRALES[k], 0.0, maximo, float(v), paso, key=f"u_{k}")

    with st.expander("Reglas activas"):
        st.caption("Desactiva una regla para ver cómo cambia el resultado.")
        grupos = [
            ("Ajustes previos", lambda r: r.conclusion.tipo != "candidato"),
            ("Elevan a riesgo alto", lambda r: r.conclusion.valor == "ROJO"),
            ("Marcan riesgo medio", lambda r: r.conclusion.valor == "AMARILLO"),
            ("Indican riesgo bajo", lambda r: r.conclusion.valor == "VERDE"),
        ]
        activas = []
        for titulo, filtro in grupos:
            st.markdown(f"**{titulo}**")
            for r in REGLAS_EDITABLES:
                if filtro(r) and st.checkbox(r.nombre, True, key=f"r_{r.id}",
                                             help=f"{r.id}: {texto_regla(r, UMBRALES)}"):
                    activas.append(r.id)

    st.caption("Prototipo académico de Sistemas Expertos, UNIMINUTO 2026-2. Todos los datos son ficticios.")

mdl = modelo()
sistema = SistemaExperto(mdl, umbrales, activas)
motor: MotorInferencia = sistema.motor
firma = (firma_datos, tuple(sorted(umbrales.items())), tuple(activas))


# ----------------------------------------------------------------------------- ficha del estudiante
def color_indicador(valor, alto, medio=None) -> str:
    if valor is None:
        return COLOR["ROJO"]
    if alto(valor):
        return COLOR["ROJO"]
    if medio and medio(valor):
        return COLOR["AMARILLO"]
    return TINTA


def ficha(res: ResultadoInferencia, nombre: str, contexto: str, clave: str) -> None:
    color = res.semaforo.value
    m = res.memoria
    st.markdown(
        f"""<div class="ficha" style="border-left-color:{COLOR[color]}">
              <div><h3>{html.escape(nombre)}</h3><div class="sub">{html.escape(contexto)}</div>
                   <div style="margin-top:.55rem">{pill(color)}</div></div>
              <div class="prob"><div class="n" style="color:{COLOR[color]}">{pct(res.probabilidad)}</div>
                   <div class="t">probabilidad de reprobar</div></div>
            </div>""",
        unsafe_allow_html=True,
    )
    u = motor.umbrales
    lab = lambda v: v is None or v < u["nota_minima"]  # noqa: E731
    indicadores = [
        ("Asistencia", fmt("asistencia", m["asistencia"]),
         color_indicador(m["asistencia"], lambda v: v < u["asist_baja"], lambda v: v <= u["asist_alta"])),
        ("Conexión a Moodle", f"{m['horas_moodle_semana']:.1f} h/semana".replace(".", ","),
         color_indicador(m["horas_moodle_semana"], lambda v: v < u["moodle_bajo"])),
        ("Laboratorio 1", fmt("nota_lab1", m["nota_lab1"]).capitalize(), color_indicador(m["nota_lab1"], lab)),
        ("Laboratorio 2", fmt("nota_lab2", m["nota_lab2"]).capitalize(), color_indicador(m["nota_lab2"], lab)),
    ]
    st.markdown(
        '<div class="indicadores">' + "".join(
            f'<div><div class="t">{t}</div><div class="v" style="color:{c}">{v}</div></div>' for t, v, c in indicadores
        ) + "</div>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.markdown("#### Por qué")
        st.markdown("\n".join(f"- {t}" for t in motivos(res, motor)))
        extra = senales_adicionales(res, motor)
        if extra:
            st.markdown('<p class="muted" style="margin:.6rem 0 .2rem 0">También se observó:</p>', unsafe_allow_html=True)
            st.markdown("\n".join(f"- {t}" for t in extra))
        for a in ajustes(res):
            st.caption(a)
    with c2:
        st.markdown("#### Qué hacer")
        st.markdown("\n".join(f"- {a}" for a in res.acciones))

    with st.expander("Ver el razonamiento del sistema"):
        t1, t2, t3 = st.tabs(["Reglas evaluadas", "Secuencia de inferencia", "Peso de cada variable"])
        with t1:
            opciones = ["ROJO", "AMARILLO", "VERDE"]
            meta = st.radio(
                "Pregunta", opciones, index=opciones.index(color), horizontal=True, label_visibility="collapsed",
                format_func=lambda c: f"¿Por qué {NIVEL[c].lower()}?" if c == color else f"¿Por qué no {NIVEL[c].lower()}?",
                key=f"meta_{clave}_{color}",
            )
            st.markdown(arbol_markdown(motor.encadenar_atras(res, meta)))
        with t2:
            st.caption("El motor revisa qué reglas se cumplen, aplica la de mayor prioridad y repite hasta que no "
                       "queda ninguna. Si hay varias conclusiones, gana el riesgo más alto.")
            filas = [{
                "Paso": d.ciclo,
                "Regla aplicada": f"{d.regla}. {motor.por_id[d.regla].nombre}",
                "Resultado": que_hizo(d.regla, d.hechos_nuevos),
                "Reglas en espera": ", ".join(x for x in d.agenda if x != d.regla) or "Ninguna",
            } for d in res.traza]
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
        with t3:
            contrib = mdl.contribuciones(m).iloc[::-1]
            fig = go.Figure(go.Bar(
                x=contrib["aporte"], y=contrib["variable"], orientation="h",
                marker_color=[COLOR["ROJO"] if a > 0 else COLOR["VERDE"] for a in contrib["aporte"]],
                hovertemplate="%{y}: %{x:.2f}<extra></extra>",
            ))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=30), template="simple_white",
                              font=dict(family="IBM Plex Sans, sans-serif", color=TINTA),
                              xaxis_title="Hacia la derecha aumenta el riesgo; hacia la izquierda lo reduce")
            st.plotly_chart(fig, width="stretch", key=f"contrib_{clave}")


# ----------------------------------------------------------------------------- encabezado
st.markdown(
    """<div class="encabezado"><h1>Alertas tempranas</h1>
       <p>Riesgo de reprobar Programación en C++ y Estructuras de Datos, al corte de la semana 3.</p></div>""",
    unsafe_allow_html=True,
)
st.write("")

tab_alertas, tab_est, tab_caso, tab_kb, tab_arq = st.tabs(
    ["Alertas", "Estudiantes", "Probar un caso", "Base de conocimiento", "Arquitectura"]
)

# ----------------------------------------------------------------------------- Alertas
with tab_alertas:
    salida = st.session_state.get("salida")
    desactualizada = bool(salida) and salida["firma"] != firma

    if not salida:
        st.markdown(
            f'<div class="vacio"><b>{len(datos)} estudiantes listos para analizar.</b><br>'
            'El sistema experto calculará el riesgo de cada uno y explicará el resultado.</div>',
            unsafe_allow_html=True,
        )
    c1, c2, c3, c4 = st.columns([1.4, 2.6, 0.9, 0.9], vertical_alignment="center")
    etiqueta_boton = "Ejecutar el sistema experto" if not salida else "Volver a ejecutar"
    if c1.button(etiqueta_boton, type="primary" if (not salida or desactualizada) else "secondary", width="stretch"):
        tabla, resultados = sistema.evaluar_curso(datos)
        st.session_state.salida = {"tabla": tabla, "resultados": resultados, "firma": firma}
        st.session_state.pop("tabla_alertas", None)
        st.rerun()
    if desactualizada:
        c2.warning("Cambió la configuración. Vuelve a ejecutar para actualizar.")
    if salida:
        t = salida["tabla"]
        exportar = t.assign(riesgo=t["semaforo"].map(NIVEL))[
            ["id", "nombre", "curso", "grupo", "riesgo", "prob_reprobar", "asistencia", "horas_moodle", "nota_lab1",
             "nota_lab2", "motivo", "accion", "acciones_especificas", "certeza", "reglas_que_sostienen",
             "reglas_disparadas"]]
        c3.download_button("CSV", exportar.to_csv(index=False).encode("utf-8-sig"), "reporte_alertas.csv",
                           "text/csv", width="stretch", help="Descargar el reporte en CSV")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            exportar.to_excel(xw, sheet_name="Alertas", index=False)
        c4.download_button("Excel", buf.getvalue(), "reporte_alertas.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch",
                           help="Descargar el reporte en Excel")

    if salida:
        tabla = salida["tabla"]
        total = len(tabla)
        conteo = {c: int((tabla["semaforo"] == c).sum()) for c in ("ROJO", "AMARILLO", "VERDE")}
        st.markdown(
            '<div class="resumen">' + "".join(
                f'<div><div class="n">{conteo[c]}</div><div class="t"><span class="marca" style="background:{COLOR[c]}">'
                f'</span>{NIVEL[c]} ({100 * conteo[c] / total:.0f} %)</div></div>' for c in conteo
            ) + '</div><div class="franja">' + "".join(
                f'<div style="width:{100 * conteo[c] / total}%;background:{COLOR[c]}"></div>' for c in conteo
            ) + "</div>",
            unsafe_allow_html=True,
        )

        f1, f2 = st.columns(2)
        sel_riesgo = f1.multiselect("Nivel de riesgo", list(NIVEL), default=list(NIVEL), format_func=NIVEL.get)
        sel_curso = f2.multiselect("Curso", sorted(tabla["curso"].unique()), placeholder="Todos los cursos")
        vista = tabla[tabla["semaforo"].isin(sel_riesgo)]
        if sel_curso:
            vista = vista[vista["curso"].isin(sel_curso)]
        vista = vista.reset_index(drop=True)

        mostrar = pd.DataFrame({
            "Estudiante": vista["nombre"],
            "Curso": vista["curso"] + ", " + vista["grupo"],
            "Riesgo": vista["semaforo"].map(NIVEL),
            "Probabilidad": vista["prob_reprobar"].clip(1, 99),
            "Motivo principal": vista["motivo"],
        })
        inverso = {v: k for k, v in NIVEL.items()}
        estilo = mostrar.style.map(
            lambda v: f"background-color:{TINTE[inverso[v]]};color:{COLOR[inverso[v]]};font-weight:600",
            subset=["Riesgo"],
        )
        st.caption("Ordenados del mayor al menor riesgo. Selecciona una fila para ver el detalle.")
        evento = st.dataframe(
            estilo, hide_index=True, width="stretch", height=420, key="tabla_alertas",
            on_select="rerun", selection_mode="single-row",
            column_config={
                "Probabilidad": st.column_config.ProgressColumn("Probabilidad", format="%.0f %%",
                                                                min_value=0, max_value=100, width="medium"),
                "Motivo principal": st.column_config.TextColumn(width="large"),
                "Riesgo": st.column_config.TextColumn(width="small"),
            },
        )

        filas_sel = evento.selection.rows if evento and evento.selection else []
        if len(vista):
            i = filas_sel[0] if filas_sel else 0
            fila = vista.iloc[i]
            st.markdown("")
            ficha(salida["resultados"][fila["id"]], fila["nombre"], f"{fila['curso']}, grupo {fila['grupo'][1:]}",
                  f"curso_{fila['id']}")
        else:
            st.info("No hay estudiantes con esos filtros.")


# ----------------------------------------------------------------------------- Estudiantes
with tab_est:
    vista = datos.copy()
    vista["asistencia"] = (100 * vista["sesiones_asistidas"] / vista["sesiones_programadas"]).round(0)
    st.caption(f"{len(vista)} estudiantes en {vista['curso'].nunique()} cursos. Asistencia promedio: "
               f"{vista['asistencia'].mean():.0f} %. Las notas vacías corresponden a laboratorios sin entregar.")
    cursos = st.multiselect("Curso", sorted(vista["curso"].unique()), placeholder="Todos los cursos", key="f_est")
    if cursos:
        vista = vista[vista["curso"].isin(cursos)]
    st.dataframe(
        pd.DataFrame({
            "Estudiante": vista["nombre"], "Curso": vista["curso"] + ", " + vista["grupo"],
            "Asistencia": vista["asistencia"], "Faltas justificadas": vista["faltas_justificadas"],
            "Moodle (h/semana)": vista["horas_moodle_semana"], "Días sin ingresar": vista["dias_sin_ingreso_moodle"],
            "Laboratorio 1": vista["nota_lab1"], "Laboratorio 2": vista["nota_lab2"],
            "Admisión matemáticas": vista["puntaje_admision_mat"], "Repite": vista["repite_materia"],
            "Trabaja": vista["trabaja_tiempo_completo"],
        }),
        hide_index=True, width="stretch", height=560,
        column_config={
            "Asistencia": st.column_config.NumberColumn(format="%.0f %%"),
            "Moodle (h/semana)": st.column_config.NumberColumn(format="%.1f"),
            "Laboratorio 1": st.column_config.NumberColumn(format="%.1f"),
            "Laboratorio 2": st.column_config.NumberColumn(format="%.1f"),
        },
    )

# ----------------------------------------------------------------------------- Probar un caso
CASOS = {
    "Asiste poco y perdió el laboratorio 1": dict(
        prog=12, asist=7, just=0, horas=2.0, dias=6, e1=True, l1=1.8, e2=True, l2=2.2, adm=55, rep=False, trab=False),
    "Asiste, pero perdió el laboratorio de memoria": dict(
        prog=12, asist=11, just=0, horas=3.5, dias=2, e1=True, l1=1.5, e2=True, l2=3.4, adm=62, rep=False, trab=False),
    "Perdió los laboratorios 1 y 2": dict(
        prog=12, asist=11, just=0, horas=3.5, dias=2, e1=True, l1=1.5, e2=True, l2=2.4, adm=62, rep=False, trab=False),
    "Asiste poco, pero rinde bien": dict(
        prog=12, asist=6, just=0, horas=5.5, dias=1, e1=True, l1=4.2, e2=True, l2=4.0, adm=70, rep=False, trab=True),
    "Tiene faltas justificadas": dict(
        prog=12, asist=8, just=2, horas=3.0, dias=3, e1=True, l1=3.4, e2=True, l2=3.3, adm=60, rep=False, trab=False),
    "Lleva días sin entrar a Moodle": dict(
        prog=12, asist=10, just=0, horas=1.0, dias=12, e1=True, l1=3.6, e2=True, l2=3.2, adm=65, rep=False, trab=False),
    "Inactivo y sin entregar el laboratorio 2": dict(
        prog=12, asist=10, just=0, horas=0.8, dias=12, e1=True, l1=3.6, e2=False, l2=0.0, adm=65, rep=False, trab=False),
    "Buen desempeño": dict(
        prog=12, asist=12, just=0, horas=6.0, dias=0, e1=True, l1=4.6, e2=True, l2=4.5, adm=82, rep=False, trab=False),
}

with tab_caso:
    st.caption("Ingresa los datos de un estudiante hipotético. Los casos de ejemplo salen de la entrevista al docente.")
    caso = st.selectbox("Caso de ejemplo", list(CASOS))
    p = CASOS[caso]
    kp = hashlib.md5(caso.encode()).hexdigest()[:6]
    with st.form("consulta", border=True):
        a, b, c = st.columns(3, gap="large")
        a.markdown("**Asistencia**")
        prog = a.number_input("Clases programadas", 1, 60, p["prog"], key=f"prog{kp}")
        asist = a.number_input("Clases asistidas", 0, 60, p["asist"], key=f"asist{kp}")
        just = a.number_input("Faltas justificadas", 0, 60, p["just"], key=f"just{kp}")
        b.markdown("**Moodle y perfil**")
        horas_m = b.number_input("Horas en Moodle por semana", 0.0, 40.0, float(p["horas"]), 0.5, format="%.1f", key=f"horas{kp}")
        dias = b.number_input("Días sin ingresar a Moodle", 0, 60, p["dias"], key=f"dias{kp}")
        adm = b.number_input("Puntaje de admisión en matemáticas", 0, 100, p["adm"], key=f"adm{kp}")
        rep = b.checkbox("Repite la materia", p["rep"], key=f"rep{kp}")
        trab = b.checkbox("Trabaja tiempo completo", p["trab"], key=f"trab{kp}")
        c.markdown("**Laboratorios**")
        e1 = c.checkbox("Entregó el laboratorio 1", p["e1"], key=f"e1{kp}")
        l1 = c.number_input("Nota del laboratorio 1", 0.0, 5.0, float(p["l1"]), 0.1, format="%.1f", key=f"l1{kp}")
        e2 = c.checkbox("Entregó el laboratorio 2", p["e2"], key=f"e2{kp}")
        l2 = c.number_input("Nota del laboratorio 2", 0.0, 5.0, float(p["l2"]), 0.1, format="%.1f", key=f"l2{kp}")
        st.form_submit_button("Evaluar este caso", type="primary")
    if asist + just > prog:
        st.error("Las clases asistidas más las faltas justificadas no pueden superar las clases programadas.")
    else:
        fila = dict(sesiones_programadas=prog, sesiones_asistidas=asist, faltas_justificadas=just,
                    horas_moodle_semana=horas_m, dias_sin_ingreso_moodle=dias,
                    nota_lab1=l1 if e1 else None, nota_lab2=l2 if e2 else None,
                    puntaje_admision_mat=adm, repite_materia=rep, trabaja_tiempo_completo=trab)
        ficha(motor.encadenar_adelante(hechos_desde_fila(fila)), "Caso de prueba", caso, f"caso_{kp}")

# ----------------------------------------------------------------------------- Base de conocimiento
with tab_kb:
    st.markdown("#### Reglas del experto")
    st.caption("Las reglas R0 a R10 salen de la entrevista al docente. P1, M1, R11 y R12 se agregaron al construir "
               "el prototipo para ordenar el razonamiento y no dejar estudiantes sin clasificar.")
    st.table(pd.DataFrame([{
        "Código": r.id, "Regla": r.nombre, "Condición y conclusión": texto_regla(r, umbrales),
        "Certeza": r.certeza, "Origen": r.origen,
        "Estado": "Activa" if r.id in activas or r.id in ("P1", "M1") else "Inactiva",
    } for r in REGLAS]).set_index("Código"))
    st.markdown(
        "**Cómo razona.** Encadenamiento hacia adelante: parte de los datos de cada estudiante y aplica las reglas "
        "por etapas (ajustes, modelo, clasificación, escalamiento). Si varias reglas se cumplen a la vez, primero va "
        "la de mayor prioridad. Cuando hay varias conclusiones, gana el riesgo más alto, salvo la excepción R7. "
        "Para explicar un resultado usa encadenamiento hacia atrás."
    )

    st.markdown("#### Modelo estadístico")
    met = mdl.metricas
    st.caption(f"Regresión logística entrenada con {met['n_entrenamiento'] + met['n_prueba']:,} estudiantes simulados "
               f"de seis semestres anteriores. En la muestra de prueba acierta el {100 * met['exactitud']:.0f} % de los "
               f"casos (AUC {met['auc']:.2f}).".replace(",", "."))
    coef = mdl.coeficientes().iloc[::-1]
    valores = coef.iloc[:, 1]
    fig = go.Figure(go.Bar(x=valores, y=coef["variable"], orientation="h",
                           marker_color=[COLOR["ROJO"] if v > 0 else COLOR["VERDE"] for v in valores]))
    fig.update_layout(height=290, margin=dict(l=10, r=10, t=10, b=30), template="simple_white",
                      font=dict(family="IBM Plex Sans, sans-serif", color=TINTA),
                      xaxis_title="Peso de cada variable: a la derecha aumenta el riesgo")
    st.plotly_chart(fig, width="stretch")

    st.markdown("#### Ontología del dominio")
    o1, o2 = st.columns(2, gap="large")
    o1.table(pd.DataFrame(RELACIONES, columns=["Entidad", "Relación", "Se relaciona con"]).set_index("Entidad"))
    o2.table(pd.DataFrame(list(GLOSARIO.items()), columns=["Concepto", "Definición"]).set_index("Concepto"))

    with st.expander("Ver los datos históricos simulados"):
        st.dataframe(historico(), hide_index=True, width="stretch")

# ----------------------------------------------------------------------------- Arquitectura
with tab_arq:
    st.graphviz_chart(
        f"""
        digraph G {{
          rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.45;
          node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=12, margin="0.18,0.08",
                color="#B9C2BC", fontcolor="{TINTA}", fillcolor="#FFFFFF"];
          edge [fontname="Helvetica", fontsize=10, color="#8A969E", fontcolor="#5B6770"];
          subgraph cluster_fuentes {{ label="Fuentes de datos simuladas"; style="dashed"; color="#B9C2BC";
            fontname="Helvetica"; fontsize=11; fontcolor="#5B6770";
            moodle [label="Moodle\\nasistencia, conexión, laboratorios"];
            notas  [label="Sistema de notas\\ny perfil de ingreso"];
            hist   [label="Semestres anteriores\\n1.200 estudiantes"]; }}
          ingesta [label="Adaptador de ingesta"];
          hechos  [label="Base de hechos"];
          reglas  [label="Base de reglas\\n(umbrales editables)"];
          modelo  [label="Modelo estadístico"];
          motor   [label="Motor de inferencia\\nencadenamiento hacia adelante", fillcolor="#E4EDF2", color="{PRIMARIO}", penwidth=1.5];
          expl    [label="Módulo de explicación\\nencadenamiento hacia atrás"];
          ui      [label="Interfaz web"];
          docente [label="Docente", shape=ellipse];
          moodle -> ingesta; notas -> ingesta;
          hist -> modelo [label=" entrena"];
          ingesta -> hechos [label=" datos del estudiante"];
          {{rank=same; hechos; reglas; modelo}}
          hechos -> motor; reglas -> motor;
          motor -> modelo [label=" consulta", style=dashed]; modelo -> motor [label=" probabilidad"];
          motor -> hechos [label=" nuevos hechos", style=dashed];
          motor -> expl [label=" pasos"]; reglas -> expl;
          motor -> ui [label=" alertas"]; expl -> ui [label=" motivos"];
          ui -> docente [dir=both, label=" consulta y ajusta"];
        }}
        """,
        width="stretch",
    )
    st.markdown(
        """
| Componente | Qué hace | Archivo |
|---|---|---|
| Adaptador de ingesta | Simula Moodle, el sistema de notas y los semestres anteriores. También acepta un CSV. | `se_alertas/ingesta_simulada.py` |
| Ontología | Define estudiantes, cursos, laboratorios, alertas y niveles de riesgo. | `se_alertas/ontologia.py` |
| Base de conocimiento | Reglas SI… ENTONCES con su certeza, origen y prioridad. | `se_alertas/base_conocimiento.py` |
| Modelo estadístico | Estima la probabilidad de reprobar a partir de semestres anteriores. | `se_alertas/modelo_estadistico.py` |
| Motor de inferencia | Aplica las reglas (hacia adelante) y reconstruye el porqué (hacia atrás). | `se_alertas/motor_inferencia.py` |
| Módulo de explicación | Traduce el razonamiento a lenguaje claro para el docente. | `se_alertas/explicacion.py` |
| Interfaz | Esta aplicación web. | `app.py` |
"""
    )
