# 🚦 Sistema Experto de Alertas Tempranas en Ciencias Básicas

Prototipo web del proyecto **Alertas Deserción** (Sistemas Expertos ISOFBL143 · UNIMINUTO · 2026-2).

Predice el riesgo de reprobar Programación en C++ y Estructuras de Datos antes de la semana 4 y lo presenta en un **semáforo (Rojo / Amarillo / Verde)** con la **justificación de cada alerta** (reglas disparadas, traza del motor y variables del modelo).

* **Técnica:** híbrida. Modelo estadístico (regresión logística entrenada con cohortes anteriores) + 15 reglas SI…ENTONCES de la entrevista al experto.
* **Motor:** encadenamiento hacia adelante para generar la alerta; encadenamiento hacia atrás para explicar ("¿por qué ROJO?", "¿por qué no VERDE?").
* **Datos:** 100 % simulados (mock de Moodle y del sistema de notas). Todos los nombres son ficticios.

La arquitectura completa está en [`ARQUITECTURA.md`](ARQUITECTURA.md).

---

## Estructura

```
alertas-desercion/
├── app.py                        # Interfaz web (Streamlit)
├── requirements.txt              # Dependencias para la nube
├── .streamlit/config.toml        # Tema y configuración
├── se_alertas/
│   ├── ingesta_simulada.py       # Adaptador Moodle SIMULADO + cohortes históricas
│   ├── ontologia.py              # Entidades, relaciones, taxonomía de riesgo
│   ├── base_conocimiento.py      # Reglas SI…ENTONCES y umbrales
│   ├── modelo_estadistico.py     # Regresión logística (scikit-learn)
│   ├── motor_inferencia.py       # Encadenamiento hacia adelante y hacia atrás
│   ├── explicacion.py            # Módulo de explicación
│   └── sistema.py                # Fachada que orquesta el flujo
├── tests/test_reglas.py          # Pruebas con los casos de la entrevista
├── ARQUITECTURA.md
└── README.md
```

---

## Publicar en la web gratis (Streamlit Community Cloud)

Resultado: una URL pública del tipo `https://alertas-desercion.streamlit.app` que cualquiera puede abrir sin instalar nada.

### Paso 1 — Crear el repositorio en GitHub

1. Entre a <https://github.com> e inicie sesión (o cree una cuenta gratuita).
2. Arriba a la derecha: **+ → New repository**.
3. *Repository name:* `alertas-desercion`. Visibilidad: **Public**. No marque "Add a README". Clic en **Create repository**.

### Paso 2 — Subir el código

**Opción A — desde el navegador (sin instalar nada):**

1. Descomprima `alertas-desercion.zip` en su computador.
2. En la página del repositorio vacío, clic en **uploading an existing file**.
3. Arrastre **el contenido** de la carpeta `alertas-desercion` (no la carpeta en sí): `app.py`, `requirements.txt`, `README.md`, `ARQUITECTURA.md` y las carpetas `se_alertas` y `tests`.
4. Clic en **Commit changes**.
5. La carpeta `.streamlit` (empieza con punto) a veces no se sube arrastrando. Si no aparece en el repositorio: **Add file → Create new file**, escriba como nombre `.streamlit/config.toml`, pegue el contenido del archivo y haga **Commit**. Es opcional: sin ella la app funciona igual, solo cambia el color del tema.

**Opción B — con Git en la terminal:**

```bash
cd alertas-desercion
git init
git add .
git commit -m "Prototipo sistema experto de alertas tempranas"
git branch -M main
git remote add origin https://github.com/SU_USUARIO/alertas-desercion.git
git push -u origin main
```

Verifique en GitHub que `app.py` y `requirements.txt` estén en la **raíz** del repositorio.

### Paso 3 — Desplegar

1. Entre a <https://share.streamlit.io> y elija **Continue with GitHub**. Autorice el acceso a sus repositorios.
2. Clic en **Create app** (arriba a la derecha) → **"Yup, I have an app"**.
3. Complete:
   * **Repository:** `SU_USUARIO/alertas-desercion`
   * **Branch:** `main`
   * **Main file path:** `app.py`
   * **App URL (opcional):** por ejemplo `alertas-desercion` → quedará `https://alertas-desercion.streamlit.app`
4. **Advanced settings → Python version: 3.12** (es el valor por defecto) → **Save**.
5. Clic en **Deploy**. La primera instalación tarda unos minutos; verá el registro de instalación a la derecha.

### Paso 4 — Compartir

Copie la URL del navegador y compártala con el docente y el equipo auditor. Cada vez que suba un cambio a GitHub, la app se actualiza sola.

### Si algo falla

| Síntoma | Solución |
|---|---|
| `ModuleNotFoundError` | `requirements.txt` no está en la raíz del repositorio o tiene otro nombre. |
| `No module named 'se_alertas'` | La carpeta `se_alertas` no se subió completa, o quedó dentro de otra carpeta. `app.py` y `se_alertas/` deben estar al mismo nivel. |
| "This app has gone to sleep" | Las apps gratuitas se duermen tras días sin visitas. Clic en **Yes, get this app back up!** y espere ~1 minuto. Ábrala unos minutos antes de la sustentación. |
| Error al instalar pandas o scikit-learn | En **Settings → General** de la app, confirme Python 3.12 y reinicie (**Reboot app**). |

### Alternativa: Render (también gratis)

1. <https://render.com> → **New → Web Service** → conecte el repositorio.
2. *Build command:* `pip install -r requirements.txt`
3. *Start command:* `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
4. Plan **Free** → **Create Web Service**. URL: `https://alertas-desercion.onrender.com`. El plan gratuito tarda ~1 minuto en despertar tras inactividad.

---

## Ejecutar localmente (opcional)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py               # abre http://localhost:8501
python -m pip install pytest && python -m pytest -q   # 11 pruebas
```

---

## Guion sugerido para la sustentación (5 minutos)

1. **👥 Estudiantes:** 160 estudiantes ficticios llegan del "Moodle simulado" (corte semana 3).
2. **🚦 Ejecutar y alertas:** pulsar *Ejecutar sistema experto*. Mostrar el conteo por color, el gráfico por grupo y la tabla ordenada por prioridad con su justificación. Descargar el Excel.
3. **🔍 Explicación:** abrir un estudiante ROJO → *¿Por qué ROJO?* (encadenamiento hacia atrás) → *Traza* (agenda y resolución de conflictos ciclo a ciclo) → *Variables del modelo*.
4. **🧪 Consulta individual:** cargar el *Caso 0 de la entrevista* (ROJO por R0, R1 y R2) y la *Pregunta 5* (la excepción R7 evita el ROJO).
5. **Auditoría cruzada:** en la barra lateral desactivar R7 o subir el umbral de ROJO a 80 % y volver a ejecutar: se ve cómo cambia el semáforo.
6. **📚 Base de conocimiento:** las 15 reglas con su origen en la entrevista y las 4 que agregó el prototipo (vacíos revelados).

---

*Prototipo académico. No usar para decisiones reales sin datos institucionales, reentrenamiento y validación con docentes.*
