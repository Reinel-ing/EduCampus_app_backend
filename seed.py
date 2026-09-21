from datetime import datetime, date, time, timedelta

from passlib.context import CryptContext

import models
from database import SessionLocal


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def run():
    db = SessionLocal()

    try:
        if db.query(models.Administrador).count() > 0:
            print("La base de datos ya tiene datos. No se vuelve a sembrar.")
            return

        # --------------------------------------------------------
        # ADMINISTRADOR
        # --------------------------------------------------------

        admin = models.Administrador(
            nombre="Administrador EduCampus",
            correo="admin@gmail.com",
            password_hash=hash_password("Admin123"),
        )

        db.add(admin)
        db.flush()

        # --------------------------------------------------------
        # GRADOS
        # --------------------------------------------------------

        grados = [
            models.Grado(nombre="Prejardín", es_preescolar=True),
            models.Grado(nombre="Jardín", es_preescolar=True),
            models.Grado(nombre="Transición", es_preescolar=True),
            models.Grado(nombre="Primero", es_preescolar=False),
            models.Grado(nombre="Segundo", es_preescolar=False),
            models.Grado(nombre="Tercero", es_preescolar=False),
            models.Grado(nombre="Cuarto", es_preescolar=False),
            models.Grado(nombre="Quinto", es_preescolar=False),
        ]

        db.add_all(grados)
        db.flush()

        grado_cuarto = grados[6]

        # --------------------------------------------------------
        # PROFESORES (docentes)
        # --------------------------------------------------------

        profesor = models.Profesor(
            nombre="Ana Martínez",
            correo="profesor@gmail.com",
            password_hash=hash_password("Profesor123"),
            especialidad="Matemáticas",
        )

        db.add(profesor)
        db.flush()

        # --------------------------------------------------------
        # ACUDIENTES
        # --------------------------------------------------------

        acudiente = models.Acudiente(
            nombre="Carlos Pérez",
            correo="acudiente@gmail.com",
            password_hash=hash_password("Acudiente123"),
            telefono="3001234567",
        )

        db.add(acudiente)
        db.flush()

        # --------------------------------------------------------
        # ESTUDIANTES
        # --------------------------------------------------------

        estudiante = models.Estudiante(
            nombre="Juan Pérez",
            correo="estudiante@gmail.com",
            password_hash=hash_password("Estudiante123"),
            grado_id=grado_cuarto.id,
            acudiente_id=acudiente.id,
        )

        db.add(estudiante)
        db.flush()

        # --------------------------------------------------------
        # CURSOS
        # --------------------------------------------------------

        curso = models.Curso(
            title="Matemáticas",
            description="Curso de matemáticas para grado cuarto",
            instructor_id=profesor.id,
            grado_id=grado_cuarto.id,
        )

        db.add(curso)
        db.flush()

        # --------------------------------------------------------
        # MATRÍCULAS
        # --------------------------------------------------------

        matricula = models.Matricula(
            student_id=estudiante.id,
            course_id=curso.id,
        )

        db.add(matricula)

        # --------------------------------------------------------
        # CALIFICACIONES
        # --------------------------------------------------------

        calificacion = models.Calificacion(
            student_id=estudiante.id,
            course_id=curso.id,
            score=4.5,
            logro="Resuelve operaciones con números enteros",
        )

        db.add(calificacion)

        # --------------------------------------------------------
        # ASISTENCIAS
        # --------------------------------------------------------

        asistencia = models.Asistencia(
            student_id=estudiante.id,
            course_id=curso.id,
            status="presente",
            fecha=date.today(),
        )

        db.add(asistencia)

        # --------------------------------------------------------
        # CONVIVENCIA
        # --------------------------------------------------------

        convivencia = models.Convivencia(
            student_id=estudiante.id,
            observacion="Participación destacada en clase",
            tipo="positiva",
            fecha=date.today(),
        )

        db.add(convivencia)

        # --------------------------------------------------------
        # ALERTAS
        # --------------------------------------------------------

        alerta = models.AlertaAlumno(
            student_id=estudiante.id,
            mensaje="Revisar avance en la tarea de matemáticas",
            severidad="baja",
        )

        db.add(alerta)

        # --------------------------------------------------------
        # MATERIAL DIDÁCTICO
        # --------------------------------------------------------

        material = models.MaterialDidactico(
            curso_id=curso.id,
            titulo="Guía de números enteros",
            archivo_url="https://example.com/materiales/numeros-enteros.pdf",
        )

        db.add(material)

        # --------------------------------------------------------
        # TAREAS (una permite video, otra no)
        # --------------------------------------------------------

        tarea_video = models.Tarea(
            curso_id=curso.id,
            titulo="Explicación en video: operaciones combinadas",
            descripcion="Graba un video explicando cómo resolver los ejercicios de la página 24",
            fecha_entrega=datetime.utcnow() + timedelta(days=7),
            permite_video=True,
        )

        tarea_escrita = models.Tarea(
            curso_id=curso.id,
            titulo="Taller escrito de números enteros",
            descripcion="Resolver el taller y subir el documento escaneado",
            fecha_entrega=datetime.utcnow() + timedelta(days=5),
            permite_video=False,
        )

        db.add_all([tarea_video, tarea_escrita])

        # --------------------------------------------------------
        # HORARIOS
        # --------------------------------------------------------

        horario = models.Horario(
            curso_id=curso.id,
            dia_semana="Lunes",
            hora_inicio=time(7, 0),
            hora_fin=time(8, 30),
        )

        db.add(horario)

        # --------------------------------------------------------
        # COMUNICADOS
        # --------------------------------------------------------

        comunicado = models.Comunicado(
            remitente="Coordinación Académica",
            titulo="Bienvenida al año escolar",
            mensaje="Damos la bienvenida a todos los estudiantes y acudientes al nuevo año escolar.",
            destinatario_rol="estudiante",
        )

        db.add(comunicado)

        db.commit()

        print("Datos de prueba insertados correctamente.")
        print("Cuentas creadas:")
        print("  admin@gmail.com / Admin123 (administrador)")
        print("  profesor@gmail.com / Profesor123 (profesor)")
        print("  acudiente@gmail.com / Acudiente123 (acudiente)")
        print("  estudiante@gmail.com / Estudiante123 (estudiante)")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    run()
