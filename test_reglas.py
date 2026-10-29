"""Pruebas de la base de reglas con los casos de la entrevista al experto.

Se usa un modelo "de juguete" que devuelve una probabilidad fija, para probar las reglas
de forma aislada del modelo estadístico.  Ejecutar:  python -m pytest -q
"""

import pytest

from se_alertas.motor_inferencia import MotorInferencia
from se_alertas.sistema import hechos_desde_fila


class ModeloFijo:
    def __init__(self, p):
        self.p = p

    def probabilidad(self, hechos):
        return self.p


def estudiante(asist=10, prog=12, just=0, horas=3.0, dias=2, lab1=4.0, lab2=4.0, repite=False, **kw):
    fila = dict(sesiones_programadas=prog, sesiones_asistidas=asist, faltas_justificadas=just,
                horas_moodle_semana=horas, dias_sin_ingreso_moodle=dias, nota_lab1=lab1, nota_lab2=lab2,
                puntaje_admision_mat=60, repite_materia=repite, trabaja_tiempo_completo=False)
    fila.update(kw)
    return hechos_desde_fila(fila)


def inferir(hechos, p):
    return MotorInferencia(ModeloFijo(p)).encadenar_adelante(hechos)


def test_caso0_entrevista_rojo():
    # 60 % asistencia (≈7/12), 2 h Moodle, lab 1 = 1,8  -> ROJO (preguntas 0 y 1)
    r = inferir(estudiante(asist=7, horas=2.0, lab1=1.8), p=80)
    assert r.semaforo.value == "ROJO"
    assert {"R0", "R1", "R2"} <= set(r.reglas_disparadas)


def test_pregunta4_amarillo_y_escalamiento():
    # Asiste 90 %+ pero lab 1 = 1,5 -> AMARILLO (R5)
    r = inferir(estudiante(asist=11, lab1=1.5, lab2=None), p=50)
    assert r.semaforo.value == "AMARILLO" and "R5" in r.reglas_disparadas
    # Si el lab 2 también queda < 3,0 -> sube a ROJO (R6)
    r = inferir(estudiante(asist=11, lab1=1.5, lab2=2.4), p=50)
    assert r.semaforo.value == "ROJO" and "R6" in r.reglas_disparadas


def test_pregunta5_excepcion_no_rojo():
    # Asiste 50 %, mucho Moodle y buenas notas -> AMARILLO aunque el modelo diga 75 %
    r = inferir(estudiante(asist=6, horas=5.0, lab1=4.0), p=75)
    assert r.semaforo.value == "AMARILLO"
    assert "R7" in r.reglas_disparadas
    assert any(c.regla == "R2" and c.anulado for c in r.candidatos)


def test_r8_descuenta_faltas_justificadas():
    # 8/12 = 66,7 % pero 2 faltas justificadas -> 8/10 = 80 %: ya no aplica R1
    r = inferir(estudiante(asist=8, just=2, lab1=2.5), p=45)
    assert r.memoria["asistencia"] == 80.0
    assert "R8" in r.reglas_disparadas and "R1" not in r.reglas_disparadas
    assert r.semaforo.value == "AMARILLO"  # R5: asistencia ≥ 70 % y lab 1 < 3,0


def test_r4_verde():
    r = inferir(estudiante(asist=11, lab1=4.2, lab2=4.0), p=15)
    assert r.semaforo.value == "VERDE" and "R4" in r.reglas_disparadas


def test_r10_inactividad_conector_o():
    r = inferir(estudiante(asist=11, dias=12), p=20)
    assert r.semaforo.value == "AMARILLO" and "R10" in r.reglas_disparadas
    r = inferir(estudiante(asist=11, lab2=None), p=20)
    assert "R10" in r.reglas_disparadas


def test_r11_completitud():
    # Probabilidad 55 % sin ninguna otra condición -> antes quedaba sin clasificar
    r = inferir(estudiante(asist=10, horas=3.0, lab1=3.6, lab2=3.4), p=55)
    assert r.reglas_disparadas[-1] == "R11" and r.semaforo.value == "AMARILLO"


def test_todos_quedan_clasificados():
    for p in range(0, 101, 5):
        for asist in range(3, 13):
            r = inferir(estudiante(asist=asist, lab1=3.2, lab2=3.1), p=p)
            assert r.candidatos, f"sin clasificar p={p} asist={asist}"


def test_encadenamiento_atras_explica_rojo():
    motor = MotorInferencia(ModeloFijo(80))
    r = motor.encadenar_adelante(estudiante(asist=7, horas=2.0, lab1=1.8))
    arbol = motor.encadenar_atras(r, "ROJO")
    sostienen = [n["id"] for n in arbol["reglas"] if n["estado"] == "sostiene"]
    assert arbol["alcanzada"] and {"R0", "R1", "R2"} <= set(sostienen)
    arbol_no = motor.encadenar_atras(r, "VERDE")
    assert not arbol_no["alcanzada"]


def test_umbral_editable():
    # El docente sube el umbral de ROJO a 85 %: con 80 % ya no dispara R2
    motor = MotorInferencia(ModeloFijo(80), umbrales={"prob_rojo": 85})
    r = motor.encadenar_adelante(estudiante(asist=11, lab1=4.0, lab2=4.0))
    assert "R2" not in r.reglas_disparadas


@pytest.mark.parametrize("desactivada", ["R7"])
def test_desactivar_regla(desactivada):
    motor = MotorInferencia(ModeloFijo(75), reglas_activas=[x for x in
                            ["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R8", "R9", "R10", "R11", "R12"]])
    r = motor.encadenar_adelante(estudiante(asist=6, horas=5.0, lab1=4.0))
    assert r.semaforo.value == "ROJO"  # sin la excepción, el modelo manda
