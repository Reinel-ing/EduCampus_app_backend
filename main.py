
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional
import io
import secrets
import shutil
import uuid

from fastapi import FastAPI, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
from dotenv import load_dotenv

import os
import models
import schemas

from database import get_db


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()


# ============================================================
# SEGURIDAD
# ============================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


# ============================================================
# SESIONES SENCILLAS
# ============================================================

# Las sesiones se guardan temporalmente en memoria.
# Se pierden cuando se reinicia el servidor.

sesiones = {}


# ============================================================
# ALMACENAMIENTO DE ARCHIVOS
# ============================================================

UPLOAD_DIR = Path(__file__).parent / "uploads" / "entregas"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# El docente elige la fecha/hora limite de una actividad en su hora local
# (Colombia, UTC-5, sin horario de verano) y se guarda tal cual, sin
# convertir a UTC. Para comparar contra "ahora" hay que restarle el mismo
# desfase a la hora del servidor (que corre en UTC).
COLOMBIA_UTC_OFFSET = timedelta(hours=-5)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DOCUMENTO_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".txt"}

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


# ============================================================
# APLICACIÓN FASTAPI
# ============================================================

app = FastAPI(
    title="EduCampus API",
    description="API backend de la plataforma educativa EduCampus",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# FUNCIONES DE SEGURIDAD
# ============================================================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:

    return pwd_context.verify(
        plain_password,
        hashed_password
    )


def requerir_admin(access_token: str) -> dict:

    sesion = sesiones.get(access_token)

    if not sesion:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida o expirada"
        )

    if sesion["rol"] != "administrador":

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede registrar nuevos usuarios"
        )

    return sesion


def requerir_sesion(access_token: str) -> dict:

    sesion = sesiones.get(access_token)

    if not sesion:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida o expirada"
        )

    return sesion


# ============================================================
# BÚSQUEDA DE CUENTAS EN LAS TABLAS POR ROL
# ============================================================

def buscar_cuenta_por_correo(db: Session, correo: str):

    correo = correo.lower().strip()

    admin = (
        db.query(models.Administrador)
        .filter(models.Administrador.correo == correo)
        .first()
    )

    if admin:
        return admin, "administrador"

    profesor = (
        db.query(models.Profesor)
        .filter(models.Profesor.correo == correo)
        .first()
    )

    if profesor:
        return profesor, "profesor"

    acudiente = (
        db.query(models.Acudiente)
        .filter(models.Acudiente.correo == correo)
        .first()
    )

    if acudiente:
        return acudiente, "acudiente"

    estudiante = (
        db.query(models.Estudiante)
        .filter(models.Estudiante.correo == correo)
        .first()
    )

    if estudiante:
        return estudiante, "estudiante"

    return None, None


def correo_en_uso(db: Session, correo: str) -> bool:

    cuenta, _ = buscar_cuenta_por_correo(db, correo)

    return cuenta is not None


# ============================================================
# RUTA PRINCIPAL
# ============================================================

@app.get("/")
def read_root():

    return {
        "message": "Bienvenido a la API de EduCampus",
        "status": "online",
        "database": "PostgreSQL / Neon"
    }


# ============================================================
# PRUEBA DE BASE DE DATOS
# ============================================================

@app.get("/health")
def health_check(
    db: Session = Depends(get_db)
):

    try:

        from sqlalchemy import text

        db.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "conectada"
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Error conectando con PostgreSQL: {str(e)}"
        )


# ============================================================
# AUTENTICACIÓN - REGISTRO
# ============================================================

@app.post(
    "/auth/registro/",
    response_model=schemas.UsuarioResponse,
    status_code=status.HTTP_201_CREATED
)
def registrar_usuario(
    usuario: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(requerir_admin)
):

    correo = str(
        usuario.correo
    ).lower().strip()

    if correo_en_uso(db, correo):

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado en el sistema"
        )

    rol = usuario.rol.lower().strip()
    password_hash = hash_password(usuario.password)
    nombre = usuario.nombre.strip()

    if rol == "administrador":

        nueva_cuenta = models.Administrador(
            nombre=nombre,
            correo=correo,
            password_hash=password_hash
        )

    elif rol in ("profesor", "docente"):

        rol = "profesor"

        nueva_cuenta = models.Profesor(
            nombre=nombre,
            correo=correo,
            password_hash=password_hash,
            especialidad=usuario.especialidad
        )

    elif rol == "acudiente":

        nueva_cuenta = models.Acudiente(
            nombre=nombre,
            correo=correo,
            password_hash=password_hash,
            telefono=usuario.telefono
        )

    else:

        if usuario.grado_id is not None:

            grado = (
                db.query(models.Grado)
                .filter(models.Grado.id == usuario.grado_id)
                .first()
            )

            if not grado:

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="El grado indicado no existe"
                )

        if usuario.acudiente_id is not None:

            acudiente = (
                db.query(models.Acudiente)
                .filter(models.Acudiente.id == usuario.acudiente_id)
                .first()
            )

            if not acudiente:

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="El acudiente indicado no existe"
                )

        nueva_cuenta = models.Estudiante(
            nombre=nombre,
            correo=correo,
            password_hash=password_hash,
            grado_id=usuario.grado_id,
            acudiente_id=usuario.acudiente_id
        )

    try:

        db.add(nueva_cuenta)
        db.commit()
        db.refresh(nueva_cuenta)

    except IntegrityError:

        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fue posible registrar el usuario"
        )

    return {
        "id": nueva_cuenta.id,
        "nombre": nueva_cuenta.nombre,
        "correo": nueva_cuenta.correo,
        "rol": rol
    }


# ============================================================
# AUTENTICACIÓN - RESTABLECER CONTRASEÑA
# ============================================================

@app.post("/auth/restablecer-password/")
def restablecer_password(
    solicitud: schemas.RestablecerPasswordRequest,
    db: Session = Depends(get_db),
    _admin: dict = Depends(requerir_admin)
):

    correo = str(solicitud.correo).lower().strip()

    cuenta, rol = buscar_cuenta_por_correo(db, correo)

    if not cuenta:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe ninguna cuenta con ese correo"
        )

    rol_solicitado = solicitud.rol.lower().strip()

    if rol_solicitado in ("profesor", "docente"):
        rol_solicitado = "profesor"

    if rol_solicitado != rol:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El rol indicado no coincide con la cuenta encontrada"
        )

    cuenta.password_hash = hash_password(solicitud.password)

    db.commit()

    return {
        "correo": cuenta.correo,
        "rol": rol,
        "message": "Contraseña restablecida correctamente"
    }


# ============================================================
# AUTENTICACIÓN - LOGIN
# ============================================================

@app.post(
    "/auth/login/",
    response_model=schemas.TokenResponse
)
def iniciar_sesion(
    credenciales: schemas.LoginRequest,
    db: Session = Depends(get_db)
):

    correo = str(
        credenciales.correo
    ).lower().strip()

    usuario, rol = buscar_cuenta_por_correo(db, correo)

    # --------------------------------------------------------
    # USUARIO NO EXISTE
    # --------------------------------------------------------

    if not usuario:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos"
        )

    # --------------------------------------------------------
    # CONTRASEÑA INCORRECTA
    # --------------------------------------------------------

    if not verify_password(
        credenciales.password,
        usuario.password_hash
    ):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos"
        )

    # --------------------------------------------------------
    # CREAR SESIÓN
    # --------------------------------------------------------

    session_id = secrets.token_urlsafe(32)

    sesiones[session_id] = {
        "usuario_id": usuario.id,
        "correo": usuario.correo,
        "nombre": usuario.nombre,
        "rol": rol,
        "creada": datetime.utcnow()
    }

    # --------------------------------------------------------
    # RESPUESTA
    # --------------------------------------------------------

    return {
        "access_token": session_id,
        "token_type": "session",
        "rol": rol,
        "nombre": usuario.nombre,
        "usuario_id": usuario.id,
        "correo": usuario.correo
    }


# ============================================================
# CERRAR SESIÓN
# ============================================================

@app.post("/auth/logout/")
def cerrar_sesion(
    access_token: str
):

    if access_token in sesiones:

        del sesiones[access_token]

        return {
            "message": "Sesión cerrada correctamente"
        }

    return {
        "message": "La sesión ya estaba cerrada"
    }


# ============================================================
# VERIFICAR SESIÓN
# ============================================================

@app.get("/auth/session/")
def verificar_sesion(
    access_token: str
):

    sesion = sesiones.get(access_token)

    if not sesion:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no válida o expirada"
        )

    return {
        "authenticated": True,
        "usuario_id": sesion["usuario_id"],
        "correo": sesion["correo"],
        "nombre": sesion["nombre"],
        "rol": sesion["rol"]
    }


# ============================================================
# GRADOS
# ============================================================

@app.post(
    "/grados/",
    status_code=status.HTTP_201_CREATED
)
def crear_grado(
    grado: schemas.GradoCreate,
    db: Session = Depends(get_db)
):

    existente = (
        db.query(models.Grado)
        .filter(
            models.Grado.nombre == grado.nombre
        )
        .first()
    )

    if existente:

        raise HTTPException(
            status_code=400,
            detail="El grado ya existe"
        )

    if grado.director_grupo_id is not None:

        profesor = (
            db.query(models.Profesor)
            .filter(models.Profesor.id == grado.director_grupo_id)
            .first()
        )

        if not profesor:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El profesor indicado como director de grupo no existe"
            )

    nuevo_grado = models.Grado(
        nombre=grado.nombre.strip(),
        es_preescolar=grado.es_preescolar,
        director_grupo_id=grado.director_grupo_id
    )

    db.add(nuevo_grado)
    db.commit()
    db.refresh(nuevo_grado)

    return nuevo_grado


@app.get("/grados/")
def listar_grados(
    db: Session = Depends(get_db)
):

    return db.query(
        models.Grado
    ).all()


@app.put("/grados/{grado_id}")
def editar_grado(
    grado_id: int,
    grado: schemas.GradoCreate,
    db: Session = Depends(get_db)
):

    existente = (
        db.query(models.Grado)
        .filter(models.Grado.id == grado_id)
        .first()
    )

    if not existente:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El grado no existe"
        )

    duplicado = (
        db.query(models.Grado)
        .filter(
            models.Grado.nombre == grado.nombre,
            models.Grado.id != grado_id
        )
        .first()
    )

    if duplicado:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un grado con ese nombre"
        )

    existente.nombre = grado.nombre.strip()
    existente.es_preescolar = grado.es_preescolar
    existente.director_grupo_id = grado.director_grupo_id

    db.commit()
    db.refresh(existente)

    return existente


@app.delete("/grados/{grado_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_grado(
    grado_id: int,
    db: Session = Depends(get_db)
):

    existente = (
        db.query(models.Grado)
        .filter(models.Grado.id == grado_id)
        .first()
    )

    if not existente:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El grado no existe"
        )

    db.delete(existente)
    db.commit()


# ============================================================
# ACUDIENTES
# ============================================================

@app.get(
    "/acudientes/",
    response_model=List[schemas.AcudienteResponse]
)
def listar_acudientes(
    db: Session = Depends(get_db)
):

    return db.query(
        models.Acudiente
    ).all()


# ============================================================
# ESTUDIANTES
# ============================================================

@app.get(
    "/estudiantes/",
    response_model=List[schemas.EstudianteResponse]
)
def listar_estudiantes(
    db: Session = Depends(get_db)
):

    return db.query(
        models.Estudiante
    ).all()


# ============================================================
# PROFESORES
# ============================================================

@app.get(
    "/profesores/",
    response_model=List[schemas.ProfesorResponse]
)
def listar_profesores(
    db: Session = Depends(get_db)
):

    return db.query(
        models.Profesor
    ).all()


# ============================================================
# CURSOS
# ============================================================

@app.post(
    "/cursos/",
    status_code=status.HTTP_201_CREATED
)
def crear_curso(
    curso: schemas.CursoCreate,
    db: Session = Depends(get_db)
):

    profesor = (
        db.query(models.Profesor)
        .filter(
            models.Profesor.id ==
            curso.instructor_id
        )
        .first()
    )

    if not profesor:

        raise HTTPException(
            status_code=404,
            detail="El profesor indicado no existe"
        )

    if curso.grado_id is not None:

        grado = (
            db.query(models.Grado)
            .filter(
                models.Grado.id ==
                curso.grado_id
            )
            .first()
        )

        if not grado:

            raise HTTPException(
                status_code=404,
                detail="El grado indicado no existe"
            )

    nuevo_curso = models.Curso(
        title=curso.title.strip(),
        description=curso.description,
        instructor_id=curso.instructor_id,
        grado_id=curso.grado_id
    )

    db.add(nuevo_curso)
    db.commit()
    db.refresh(nuevo_curso)

    return nuevo_curso


@app.get("/cursos/")
def listar_cursos(
    instructor_id: int | None = None,
    student_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.Curso)

    if instructor_id is not None:

        query = query.filter(models.Curso.instructor_id == instructor_id)

    if student_id is not None:

        query = (
            query.join(
                models.Matricula,
                models.Matricula.course_id == models.Curso.id
            )
            .filter(models.Matricula.student_id == student_id)
        )

    return query.all()


# ============================================================
# MATRÍCULAS
# ============================================================

@app.post(
    "/matriculas/",
    status_code=status.HTTP_201_CREATED
)
def crear_matricula(
    mat: schemas.MatriculaCreate,
    db: Session = Depends(get_db)
):

    estudiante = (
        db.query(models.Estudiante)
        .filter(
            models.Estudiante.id ==
            mat.student_id
        )
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=404,
            detail="El estudiante no existe"
        )

    curso = (
        db.query(models.Curso)
        .filter(
            models.Curso.id ==
            mat.course_id
        )
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=404,
            detail="El curso no existe"
        )

    existente = (
        db.query(models.Matricula)
        .filter(
            models.Matricula.student_id ==
            mat.student_id,
            models.Matricula.course_id ==
            mat.course_id
        )
        .first()
    )

    if existente:

        raise HTTPException(
            status_code=400,
            detail="El estudiante ya está matriculado en este curso"
        )

    nueva_matricula = models.Matricula(
        student_id=mat.student_id,
        course_id=mat.course_id
    )

    db.add(nueva_matricula)
    db.commit()
    db.refresh(nueva_matricula)

    return nueva_matricula


@app.get(
    "/cursos/{curso_id}/estudiantes/",
    response_model=List[schemas.EstudianteResponse]
)
def listar_estudiantes_del_curso(
    curso_id: int,
    db: Session = Depends(get_db)
):

    matriculas = (
        db.query(models.Matricula)
        .filter(models.Matricula.course_id == curso_id)
        .all()
    )

    return [m.estudiante for m in matriculas if m.estudiante is not None]


# ============================================================
# CALIFICACIONES
# ============================================================

@app.post(
    "/calificaciones/",
    response_model=schemas.CalificacionResponse,
    status_code=status.HTTP_201_CREATED
)
def crear_calificacion(
    cal: schemas.CalificacionCreate,
    db: Session = Depends(get_db)
):

    estudiante = (
        db.query(models.Estudiante)
        .filter(
            models.Estudiante.id ==
            cal.student_id
        )
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=404,
            detail="El estudiante no existe"
        )

    curso = (
        db.query(models.Curso)
        .filter(
            models.Curso.id ==
            cal.course_id
        )
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=404,
            detail="El curso no existe"
        )

    existente = (
        db.query(models.Calificacion)
        .filter(
            models.Calificacion.student_id == cal.student_id,
            models.Calificacion.course_id == cal.course_id,
            models.Calificacion.periodo == cal.periodo
        )
        .first()
    )

    if existente:

        existente.score = cal.score
        existente.logro = cal.logro
        existente.fecha = datetime.utcnow()

        db.commit()
        db.refresh(existente)

        return existente

    nueva_calificacion = models.Calificacion(
        student_id=cal.student_id,
        course_id=cal.course_id,
        score=cal.score,
        logro=cal.logro,
        periodo=cal.periodo
    )

    db.add(nueva_calificacion)
    db.commit()
    db.refresh(nueva_calificacion)

    return nueva_calificacion


@app.get(
    "/calificaciones/",
    response_model=List[schemas.CalificacionResponse]
)
def listar_calificaciones(
    student_id: int | None = None,
    course_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.Calificacion)

    if student_id is not None:

        query = query.filter(models.Calificacion.student_id == student_id)

    if course_id is not None:

        query = query.filter(models.Calificacion.course_id == course_id)

    return query.all()


@app.delete(
    "/calificaciones/{calificacion_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_calificacion(
    calificacion_id: int,
    db: Session = Depends(get_db)
):

    existente = (
        db.query(models.Calificacion)
        .filter(models.Calificacion.id == calificacion_id)
        .first()
    )

    if not existente:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La calificación no existe"
        )

    db.delete(existente)
    db.commit()


# ============================================================
# OBSERVACIONES DEL BOLETÍN
# ============================================================

@app.get(
    "/observaciones/",
    response_model=List[schemas.ObservacionResponse]
)
def listar_observaciones(
    student_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.Observacion)

    if student_id is not None:

        query = query.filter(models.Observacion.student_id == student_id)

    return query.all()


@app.post(
    "/observaciones/",
    response_model=schemas.ObservacionResponse,
    status_code=status.HTTP_201_CREATED
)
def guardar_observacion(
    obs: schemas.ObservacionCreate,
    db: Session = Depends(get_db)
):

    estudiante = (
        db.query(models.Estudiante)
        .filter(models.Estudiante.id == obs.student_id)
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El estudiante no existe"
        )

    existente = (
        db.query(models.Observacion)
        .filter(
            models.Observacion.student_id == obs.student_id,
            models.Observacion.periodo == obs.periodo
        )
        .first()
    )

    if existente:

        existente.texto = obs.texto
        existente.fecha = datetime.utcnow()

        db.commit()
        db.refresh(existente)

        return existente

    nueva_observacion = models.Observacion(
        student_id=obs.student_id,
        periodo=obs.periodo,
        texto=obs.texto
    )

    db.add(nueva_observacion)
    db.commit()
    db.refresh(nueva_observacion)

    return nueva_observacion


@app.get(
    "/observaciones/{student_id}/{periodo}",
    response_model=schemas.ObservacionResponse
)
def obtener_observacion(
    student_id: int,
    periodo: str,
    db: Session = Depends(get_db)
):

    observacion = (
        db.query(models.Observacion)
        .filter(
            models.Observacion.student_id == student_id,
            models.Observacion.periodo == periodo.upper()
        )
        .first()
    )

    if not observacion:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay observación registrada para este periodo"
        )

    return observacion


# ============================================================
# ASISTENCIAS
# ============================================================

@app.post(
    "/asistencias/",
    status_code=status.HTTP_201_CREATED
)
def registrar_asistencia(
    asis: schemas.AsistenciaCreate,
    db: Session = Depends(get_db)
):

    estudiante = (
        db.query(models.Estudiante)
        .filter(
            models.Estudiante.id ==
            asis.student_id
        )
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=404,
            detail="El estudiante no existe"
        )

    curso = (
        db.query(models.Curso)
        .filter(
            models.Curso.id ==
            asis.course_id
        )
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=404,
            detail="El curso no existe"
        )

    fecha = asis.fecha or datetime.utcnow().date()

    if fecha > datetime.utcnow().date():

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede registrar asistencia de una fecha futura"
        )

    existente = (
        db.query(models.Asistencia)
        .filter(
            models.Asistencia.student_id == asis.student_id,
            models.Asistencia.course_id == asis.course_id,
            models.Asistencia.fecha == fecha
        )
        .first()
    )

    if existente:

        existente.status = asis.status

        db.commit()
        db.refresh(existente)

        return existente

    nueva_asistencia = models.Asistencia(
        student_id=asis.student_id,
        course_id=asis.course_id,
        status=asis.status,
        fecha=fecha
    )

    db.add(nueva_asistencia)
    db.commit()
    db.refresh(nueva_asistencia)

    return nueva_asistencia


@app.get(
    "/asistencias/",
    response_model=List[schemas.AsistenciaResponse]
)
def listar_asistencias(
    course_id: int | None = None,
    student_id: int | None = None,
    fecha: date | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.Asistencia)

    if course_id is not None:
        query = query.filter(models.Asistencia.course_id == course_id)

    if student_id is not None:
        query = query.filter(models.Asistencia.student_id == student_id)

    if fecha is not None:
        query = query.filter(models.Asistencia.fecha == fecha)

    return query.order_by(models.Asistencia.fecha.desc()).all()


# ============================================================
# ASISTENCIA DE DOCENTES
# ============================================================

@app.post(
    "/asistencia-docentes/",
    response_model=schemas.AsistenciaDocenteResponse,
    status_code=status.HTTP_201_CREATED
)
def registrar_asistencia_docente(
    asis: schemas.AsistenciaDocenteCreate,
    db: Session = Depends(get_db)
):

    profesor = (
        db.query(models.Profesor)
        .filter(models.Profesor.id == asis.profesor_id)
        .first()
    )

    if not profesor:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El docente no existe"
        )

    fecha = asis.fecha or datetime.utcnow().date()

    if fecha > datetime.utcnow().date():

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede registrar asistencia de una fecha futura"
        )

    existente = (
        db.query(models.AsistenciaDocente)
        .filter(
            models.AsistenciaDocente.profesor_id == asis.profesor_id,
            models.AsistenciaDocente.fecha == fecha
        )
        .first()
    )

    if existente:

        existente.presente = asis.presente
        existente.completo = asis.completo
        existente.observacion = asis.observacion

        db.commit()
        db.refresh(existente)

        return existente

    nueva = models.AsistenciaDocente(
        profesor_id=asis.profesor_id,
        fecha=fecha,
        presente=asis.presente,
        completo=asis.completo,
        observacion=asis.observacion
    )

    db.add(nueva)
    db.commit()
    db.refresh(nueva)

    return nueva


@app.get(
    "/asistencia-docentes/",
    response_model=List[schemas.AsistenciaDocenteResponse]
)
def listar_asistencia_docentes(
    fecha: date | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.AsistenciaDocente)

    if fecha is not None:
        query = query.filter(models.AsistenciaDocente.fecha == fecha)

    return query.all()


# ============================================================
# CONVIVENCIA
# ============================================================

@app.post(
    "/convivencia/",
    response_model=schemas.ConvivenciaResponse,
    status_code=status.HTTP_201_CREATED
)
def registrar_convivencia(
    conv: schemas.ConvivenciaCreate,
    db: Session = Depends(get_db)
):

    estudiante = (
        db.query(models.Estudiante)
        .filter(
            models.Estudiante.id ==
            conv.student_id
        )
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=404,
            detail="El estudiante no existe"
        )

    nuevo_registro = models.Convivencia(
        student_id=conv.student_id,
        titulo=conv.titulo,
        observacion=conv.observacion,
        tipo=conv.tipo,
        fecha=conv.fecha or datetime.utcnow().date()
    )

    db.add(nuevo_registro)
    db.commit()
    db.refresh(nuevo_registro)

    return nuevo_registro


@app.get(
    "/convivencia/",
    response_model=List[schemas.ConvivenciaResponse]
)
def listar_convivencia(
    student_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.Convivencia)

    if student_id is not None:

        query = query.filter(models.Convivencia.student_id == student_id)

    return query.order_by(models.Convivencia.fecha.desc()).all()


@app.put(
    "/convivencia/{convivencia_id}/seguimiento",
    response_model=schemas.ConvivenciaResponse
)
def actualizar_seguimiento_convivencia(
    convivencia_id: int,
    datos: schemas.SeguimientoConvivenciaRequest,
    db: Session = Depends(get_db)
):

    registro = (
        db.query(models.Convivencia)
        .filter(models.Convivencia.id == convivencia_id)
        .first()
    )

    if not registro:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El registro no existe"
        )

    registro.seguimiento_realizado = True

    if datos.nota_seguimiento is not None:
        registro.nota_seguimiento = datos.nota_seguimiento

    db.commit()
    db.refresh(registro)

    return registro


@app.delete(
    "/convivencia/{convivencia_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_convivencia(
    convivencia_id: int,
    db: Session = Depends(get_db)
):

    registro = (
        db.query(models.Convivencia)
        .filter(models.Convivencia.id == convivencia_id)
        .first()
    )

    if not registro:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El registro no existe"
        )

    db.delete(registro)
    db.commit()


# ============================================================
# ALERTAS
# ============================================================

@app.post(
    "/alertas/",
    response_model=schemas.AlertaResponse,
    status_code=status.HTTP_201_CREATED
)
def registrar_alerta(
    alerta: schemas.AlertaCreate,
    db: Session = Depends(get_db)
):

    estudiante = (
        db.query(models.Estudiante)
        .filter(
            models.Estudiante.id ==
            alerta.student_id
        )
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=404,
            detail="El estudiante no existe"
        )

    nueva_alerta = models.AlertaAlumno(
        student_id=alerta.student_id,
        docente_nombre=alerta.docente_nombre,
        mensaje=alerta.mensaje,
        severidad=alerta.severidad
    )

    db.add(nueva_alerta)

    if estudiante.acudiente_id is not None:

        nueva_notificacion = models.Notificacion(
            acudiente_id=estudiante.acudiente_id,
            estudiante_id=estudiante.id,
            titulo=f"Aviso sobre {estudiante.nombre}",
            mensaje=alerta.mensaje,
            tipo="alerta"
        )

        db.add(nueva_notificacion)

    db.commit()
    db.refresh(nueva_alerta)

    return nueva_alerta


@app.get(
    "/alertas/",
    response_model=List[schemas.AlertaResponse]
)
def listar_alertas(
    student_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.AlertaAlumno)

    if student_id is not None:

        query = query.filter(models.AlertaAlumno.student_id == student_id)

    return query.order_by(models.AlertaAlumno.fecha.desc()).all()


@app.put(
    "/alertas/{alerta_id}/atender",
    response_model=schemas.AlertaResponse
)
def atender_alerta(
    alerta_id: int,
    datos: schemas.AtenderAlertaRequest,
    db: Session = Depends(get_db)
):

    alerta = (
        db.query(models.AlertaAlumno)
        .filter(models.AlertaAlumno.id == alerta_id)
        .first()
    )

    if not alerta:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La alerta no existe"
        )

    alerta.atendida = True

    if datos.respuesta_admin is not None:
        alerta.respuesta_admin = datos.respuesta_admin

    db.commit()
    db.refresh(alerta)

    return alerta


# ============================================================
# NOTIFICACIONES Y AVISO DE RECOGIDA
# ============================================================

@app.post(
    "/avisar-recogida/",
    response_model=schemas.AvisoRecogidaResponse
)
def avisar_recogida(
    solicitud: schemas.AvisoRecogidaRequest,
    db: Session = Depends(get_db),
    sesion: dict = Depends(requerir_sesion)
):

    curso = (
        db.query(models.Curso)
        .filter(models.Curso.id == solicitud.course_id)
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El curso no existe"
        )

    if sesion["rol"] == "profesor" and curso.instructor_id != sesion["usuario_id"]:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este curso no te pertenece"
        )

    elif sesion["rol"] not in ("profesor", "administrador"):

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un docente o administrador puede enviar este aviso"
        )

    matriculas = (
        db.query(models.Matricula)
        .filter(models.Matricula.course_id == curso.id)
        .all()
    )

    notificados = 0
    avisos_whatsapp = []

    for matricula in matriculas:

        estudiante = matricula.estudiante

        if not estudiante or estudiante.acudiente_id is None:
            continue

        mensaje = (
            f"La clase de {curso.title} ha finalizado. "
            f"Ya puede pasar a recoger a {estudiante.nombre} en el colegio."
        )

        notificacion = models.Notificacion(
            acudiente_id=estudiante.acudiente_id,
            estudiante_id=estudiante.id,
            titulo="Ya puede recoger a su hijo(a)",
            mensaje=mensaje,
            tipo="recogida"
        )

        db.add(notificacion)
        notificados += 1

        acudiente = (
            db.query(models.Acudiente)
            .filter(models.Acudiente.id == estudiante.acudiente_id)
            .first()
        )

        if acudiente and acudiente.telefono:

            avisos_whatsapp.append({
                "telefono": acudiente.telefono,
                "mensaje": mensaje
            })

    db.add(models.ClaseFinalizada(curso_id=curso.id))

    db.commit()

    return {
        "acudientes_notificados": notificados,
        "curso": curso.title,
        "whatsapp": avisos_whatsapp
    }


@app.get(
    "/notificaciones/{acudiente_id}/",
    response_model=List[schemas.NotificacionResponse]
)
def listar_notificaciones(
    acudiente_id: int,
    db: Session = Depends(get_db)
):

    return (
        db.query(models.Notificacion)
        .filter(models.Notificacion.acudiente_id == acudiente_id)
        .order_by(models.Notificacion.fecha.desc())
        .all()
    )


@app.get(
    "/notificaciones/docente/{profesor_id}/",
    response_model=List[schemas.NotificacionResponse]
)
def listar_notificaciones_docente(
    profesor_id: int,
    db: Session = Depends(get_db)
):

    return (
        db.query(models.Notificacion)
        .filter(models.Notificacion.profesor_id == profesor_id)
        .order_by(models.Notificacion.fecha.desc())
        .all()
    )


@app.post("/notificaciones/{notificacion_id}/marcar-leida/")
def marcar_notificacion_leida(
    notificacion_id: int,
    db: Session = Depends(get_db)
):

    notificacion = (
        db.query(models.Notificacion)
        .filter(models.Notificacion.id == notificacion_id)
        .first()
    )

    if not notificacion:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La notificación no existe"
        )

    notificacion.leida = True

    db.commit()

    return {"message": "Notificación marcada como leída"}


# ============================================================
# MATERIAL DIDÁCTICO
# ============================================================

@app.post(
    "/materiales/",
    response_model=schemas.MaterialResponse,
    status_code=status.HTTP_201_CREATED
)
def subir_material(
    mat: schemas.MaterialCreate,
    db: Session = Depends(get_db)
):

    curso = (
        db.query(models.Curso)
        .filter(
            models.Curso.id ==
            mat.curso_id
        )
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=404,
            detail="El curso no existe"
        )

    nuevo_material = models.MaterialDidactico(
        curso_id=mat.curso_id,
        titulo=mat.titulo.strip(),
        descripcion=mat.descripcion.strip(),
        materia=mat.materia.strip(),
        enlace=mat.enlace.strip(),
        archivo_nombre=mat.archivo_nombre,
        archivo_base64=mat.archivo_base64,
    )

    db.add(nuevo_material)
    db.commit()
    db.refresh(nuevo_material)

    return nuevo_material


@app.get(
    "/materiales/",
    response_model=List[schemas.MaterialResponse]
)
def listar_materiales(
    curso_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.MaterialDidactico)

    if curso_id is not None:

        query = query.filter(models.MaterialDidactico.curso_id == curso_id)

    return query.order_by(models.MaterialDidactico.fecha_creacion.desc()).all()


@app.delete(
    "/materiales/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_material(
    material_id: int,
    db: Session = Depends(get_db)
):

    existente = (
        db.query(models.MaterialDidactico)
        .filter(models.MaterialDidactico.id == material_id)
        .first()
    )

    if not existente:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El material no existe"
        )

    db.delete(existente)
    db.commit()


# ============================================================
# TAREAS
# ============================================================

@app.post(
    "/tareas/",
    response_model=schemas.TareaResponse,
    status_code=status.HTTP_201_CREATED
)
def crear_tarea(
    tar: schemas.TareaCreate,
    db: Session = Depends(get_db)
):

    curso = (
        db.query(models.Curso)
        .filter(
            models.Curso.id ==
            tar.curso_id
        )
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=404,
            detail="El curso no existe"
        )

    nueva_tarea = models.Tarea(
        curso_id=tar.curso_id,
        titulo=tar.titulo,
        descripcion=tar.descripcion,
        fecha_entrega=tar.fecha_entrega,
        permite_video=tar.permite_video
    )

    db.add(nueva_tarea)
    db.commit()
    db.refresh(nueva_tarea)

    return nueva_tarea


@app.get(
    "/tareas/",
    response_model=List[schemas.TareaResponse]
)
def listar_tareas(
    curso_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.Tarea)

    if curso_id is not None:

        query = query.filter(models.Tarea.curso_id == curso_id)

    return query.order_by(models.Tarea.fecha_entrega).all()


# ============================================================
# ENTREGAS DE ACTIVIDADES (el acudiente sube el trabajo)
# ============================================================

async def guardar_archivo_subido(
    archivo: UploadFile,
    destino: Path
) -> None:

    tamano = 0

    with destino.open("wb") as buffer:

        while True:

            fragmento = await archivo.read(1024 * 1024)

            if not fragmento:
                break

            tamano += len(fragmento)

            if tamano > MAX_UPLOAD_BYTES:

                buffer.close()
                destino.unlink(missing_ok=True)

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo supera el tamaño máximo permitido (200 MB)"
                )

            buffer.write(fragmento)


@app.post(
    "/tareas/{tarea_id}/entregas/",
    response_model=schemas.EntregaResponse,
    status_code=status.HTTP_201_CREATED
)
async def subir_entrega(
    tarea_id: int,
    student_id: int = Form(...),
    acudiente_id: Optional[int] = Form(None),
    comentario: Optional[str] = Form(None),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    tarea = (
        db.query(models.Tarea)
        .filter(models.Tarea.id == tarea_id)
        .first()
    )

    if not tarea:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La actividad no existe"
        )

    if datetime.utcnow() + COLOMBIA_UTC_OFFSET > tarea.fecha_entrega:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El plazo de entrega de esta actividad ya venció"
        )

    estudiante = (
        db.query(models.Estudiante)
        .filter(models.Estudiante.id == student_id)
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El estudiante no existe"
        )

    if acudiente_id is not None:

        acudiente = (
            db.query(models.Acudiente)
            .filter(models.Acudiente.id == acudiente_id)
            .first()
        )

        if not acudiente:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El acudiente indicado no existe"
            )

    extension = Path(archivo.filename or "").suffix.lower()
    es_video = extension in VIDEO_EXTENSIONS

    if es_video and not tarea.permite_video:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta actividad no admite el envío de videos"
        )

    if not es_video and extension not in DOCUMENTO_EXTENSIONS:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no permitido"
        )

    nombre_archivo = f"{uuid.uuid4().hex}{extension}"
    destino = UPLOAD_DIR / nombre_archivo

    await guardar_archivo_subido(archivo, destino)

    nueva_entrega = models.TareaEntrega(
        tarea_id=tarea_id,
        student_id=student_id,
        acudiente_id=acudiente_id,
        archivo_path=str(destino.relative_to(UPLOAD_DIR.parent.parent)),
        archivo_tipo="video" if es_video else "documento",
        nombre_original=archivo.filename or nombre_archivo,
        comentario=comentario
    )

    db.add(nueva_entrega)

    try:

        db.commit()
        db.refresh(nueva_entrega)

    except IntegrityError:

        db.rollback()
        destino.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una entrega de este estudiante para esta actividad"
        )

    curso = (
        db.query(models.Curso)
        .filter(models.Curso.id == tarea.curso_id)
        .first()
    )

    if curso and curso.instructor_id:

        notificacion = models.Notificacion(
            profesor_id=curso.instructor_id,
            estudiante_id=student_id,
            titulo="Nueva entrega",
            mensaje=f"{estudiante.nombre} entregó la actividad \"{tarea.titulo}\".",
            tipo="entrega"
        )

        db.add(notificacion)
        db.commit()

    return nueva_entrega


@app.get(
    "/tareas/{tarea_id}/entregas/",
    response_model=List[schemas.EntregaResponse]
)
def listar_entregas(
    tarea_id: int,
    db: Session = Depends(get_db)
):

    return (
        db.query(models.TareaEntrega)
        .filter(models.TareaEntrega.tarea_id == tarea_id)
        .all()
    )


@app.get("/entregas/{entrega_id}/archivo")
def descargar_entrega(
    entrega_id: int,
    db: Session = Depends(get_db)
):

    entrega = (
        db.query(models.TareaEntrega)
        .filter(models.TareaEntrega.id == entrega_id)
        .first()
    )

    if not entrega:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La entrega no existe"
        )

    ruta_archivo = Path(__file__).parent / entrega.archivo_path

    if not ruta_archivo.exists():

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El archivo ya no está disponible"
        )

    return FileResponse(
        path=ruta_archivo,
        filename=entrega.nombre_original
    )


@app.put(
    "/entregas/{entrega_id}/calificar",
    response_model=schemas.EntregaResponse
)
def calificar_entrega(
    entrega_id: int,
    datos: schemas.CalificarEntregaRequest,
    db: Session = Depends(get_db)
):

    entrega = (
        db.query(models.TareaEntrega)
        .filter(models.TareaEntrega.id == entrega_id)
        .first()
    )

    if not entrega:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La entrega no existe"
        )

    entrega.nota = datos.nota
    entrega.retroalimentacion = datos.retroalimentacion

    db.commit()
    db.refresh(entrega)

    return entrega


# ============================================================
# HORARIOS
# ============================================================

@app.post(
    "/horarios/",
    response_model=schemas.HorarioResponse,
    status_code=status.HTTP_201_CREATED
)
def crear_horario(
    hor: schemas.HorarioCreate,
    db: Session = Depends(get_db)
):

    curso = (
        db.query(models.Curso)
        .filter(
            models.Curso.id ==
            hor.curso_id
        )
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=404,
            detail="El curso no existe"
        )

    nuevo_horario = models.Horario(
        curso_id=hor.curso_id,
        dia_semana=hor.dia_semana,
        hora_inicio=hor.hora_inicio,
        hora_fin=hor.hora_fin
    )

    db.add(nuevo_horario)
    db.commit()
    db.refresh(nuevo_horario)

    return nuevo_horario


@app.get(
    "/horarios/",
    response_model=List[schemas.HorarioResponse]
)
def listar_horarios(
    curso_id: int | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(models.Horario)

    if curso_id is not None:

        query = query.filter(models.Horario.curso_id == curso_id)

    return query.all()


@app.delete(
    "/horarios/{horario_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_horario(
    horario_id: int,
    db: Session = Depends(get_db)
):

    existente = (
        db.query(models.Horario)
        .filter(models.Horario.id == horario_id)
        .first()
    )

    if not existente:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El horario no existe"
        )

    db.delete(existente)
    db.commit()


@app.delete(
    "/cursos/{curso_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_curso(
    curso_id: int,
    db: Session = Depends(get_db)
):

    existente = (
        db.query(models.Curso)
        .filter(models.Curso.id == curso_id)
        .first()
    )

    if not existente:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El curso no existe"
        )

    db.delete(existente)
    db.commit()


# ============================================================
# COMUNICADOS
# ============================================================

@app.post(
    "/comunicados/",
    status_code=status.HTTP_201_CREATED
)
def crear_comunicado(
    com: schemas.ComunicadoCreate,
    db: Session = Depends(get_db)
):

    nuevo_comunicado = models.Comunicado(
        remitente=com.remitente,
        titulo=com.titulo,
        mensaje=com.mensaje,
        destinatario_rol=com.destinatario_rol,
        fecha=com.fecha or datetime.utcnow()
    )

    db.add(nuevo_comunicado)
    db.commit()
    db.refresh(nuevo_comunicado)

    return nuevo_comunicado


# ============================================================
# BOLETÍN EN PDF
# ============================================================

PERIODOS_VALIDOS = {"I", "II", "III", "IV"}

DIRECTOR_NOMBRE = os.getenv("DIRECTOR_NOMBRE", "MARIBEL ROJAS PAYARES")

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_COLMAS_PATH = ASSETS_DIR / "logo_colmas.png"
FIRMA_DIRECTORA_PATH = ASSETS_DIR / "firma_directora.png"

COLOR_DORADO = colors.HexColor("#F9C65F")
COLOR_DORADO_CLARO = colors.HexColor("#FFFFCC")
COLOR_MARRON = colors.HexColor("#8B5E34")


def calcular_desempeno(score: float) -> str:

    if score >= 4.6:
        return "SUPERIOR"

    if score >= 4.0:
        return "ALTO"

    if score >= 3.0:
        return "BÁSICO"

    return "BAJO"


@app.get("/estudiantes/{estudiante_id}/boletin/")
def descargar_boletin(
    estudiante_id: int,
    periodo: str = "I",
    db: Session = Depends(get_db)
):

    periodo = periodo.strip().upper()

    if periodo not in PERIODOS_VALIDOS:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El periodo debe ser I, II, III o IV"
        )

    estudiante = (
        db.query(models.Estudiante)
        .filter(models.Estudiante.id == estudiante_id)
        .first()
    )

    if not estudiante:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El estudiante no existe"
        )

    matriculas = (
        db.query(models.Matricula)
        .filter(models.Matricula.student_id == estudiante_id)
        .all()
    )

    if not matriculas:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El estudiante no está matriculado en ningún curso"
        )

    cursos_sin_notas = []
    areas = []

    for matricula in matriculas:

        curso = matricula.curso

        calificacion = (
            db.query(models.Calificacion)
            .filter(
                models.Calificacion.student_id == estudiante_id,
                models.Calificacion.course_id == curso.id,
                models.Calificacion.periodo == periodo
            )
            .first()
        )

        if not calificacion:

            cursos_sin_notas.append(curso.title)
            continue

        areas.append((curso, calificacion))

    if cursos_sin_notas:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No se puede generar el boletín del periodo {periodo} porque faltan notas en: "
                + ", ".join(cursos_sin_notas)
            )
        )

    observacion = (
        db.query(models.Observacion)
        .filter(
            models.Observacion.student_id == estudiante_id,
            models.Observacion.periodo == periodo
        )
        .first()
    )

    grado = estudiante.grado

    docente_firma = None

    if grado and grado.director_grupo:
        docente_firma = grado.director_grupo.nombre
    elif areas:
        docente_firma = areas[0][0].profesor.nombre if areas[0][0].profesor else None

    buffer = io.BytesIO()

    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"Informe académico - {estudiante.nombre}",
        topMargin=36,
        bottomMargin=36
    )

    estilos = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle(
        "TituloInforme",
        parent=estilos["Title"],
        fontSize=16,
        spaceAfter=4,
        textColor=COLOR_MARRON
    )

    estilo_area = ParagraphStyle(
        "AreaNombre",
        parent=estilos["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=COLOR_MARRON
    )

    estilo_logro = ParagraphStyle(
        "LogroTexto",
        parent=estilos["Normal"],
        fontSize=9,
        leading=12
    )

    estilo_observaciones = ParagraphStyle(
        "Observaciones",
        parent=estilos["Normal"],
        fontSize=10,
        leading=14
    )

    elementos = []

    if LOGO_COLMAS_PATH.exists():

        logo = Image(str(LOGO_COLMAS_PATH), width=70, height=70)
        logo.hAlign = "CENTER"

        encabezado_institucion = Table(
            [[logo, Paragraph(
                "<b>Colegio Manantial de Sabiduría</b><br/>\"COLMAS\"<br/>"
                "El principio de la sabiduría es el temor de Jehová. Prov. 1:7",
                ParagraphStyle(
                    "InstitucionTexto",
                    parent=estilos["Normal"],
                    fontSize=9,
                    textColor=COLOR_MARRON,
                    alignment=1
                )
            )]],
            colWidths=[80, 400]
        )
        encabezado_institucion.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ]))

        elementos.append(encabezado_institucion)

    else:

        elementos.append(Paragraph("Colegio Manantial de Sabiduría (COLMAS)", estilos["Heading4"]))

    elementos.append(Spacer(1, 6))
    elementos.append(Paragraph("Informe académico", estilo_titulo))

    linea_separadora = Table([[""]], colWidths=[480], rowHeights=[2])
    linea_separadora.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, COLOR_MARRON),
    ]))
    elementos.append(linea_separadora)
    elementos.append(Spacer(1, 10))

    info_estudiante = [
        [
            Paragraph(f"<b>ESTUDIANTE:</b> {estudiante.nombre.upper()}", estilos["Normal"]),
            Paragraph(f"<b>PERIODO:</b> {periodo}", estilos["Normal"]),
        ],
        [
            Paragraph(f"<b>GRADO:</b> {grado.nombre if grado else '-'}", estilos["Normal"]),
            Paragraph(f"<b>FECHA:</b> {datetime.utcnow().strftime('%d/%m/%Y')}", estilos["Normal"]),
        ],
    ]

    tabla_info = Table(info_estudiante, colWidths=[280, 200])
    tabla_info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    elementos.append(tabla_info)
    elementos.append(Spacer(1, 16))

    for curso, calificacion in areas:

        nombre_area = curso.title.upper()
        desempeno = calcular_desempeno(calificacion.score)
        nota = f"{calificacion.score:.1f}".replace(".", ",")

        logros_html = "<br/>".join(
            f"• {linea.strip()}"
            for linea in (calificacion.logro or "Sin logros registrados").split("\n")
            if linea.strip()
        ) or "Sin logros registrados"

        encabezado = Table(
            [[Paragraph(nombre_area, estilo_area), Paragraph("DESEMPEÑO", estilo_area)]],
            colWidths=[340, 140]
        )
        encabezado.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_DORADO),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ]))

        cuerpo = Table(
            [[
                Paragraph(logros_html, estilo_logro),
                Paragraph(desempeno, estilo_logro),
                Paragraph(nota, estilo_logro),
            ]],
            colWidths=[340, 80, 60]
        )
        cuerpo.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MARRON),
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_DORADO_CLARO),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (2, 0), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))

        elementos.append(encabezado)
        elementos.append(cuerpo)
        elementos.append(Spacer(1, 10))

    elementos.append(Spacer(1, 10))

    encabezado_obs = Table([[Paragraph("OBSERVACIONES", estilo_area)]], colWidths=[480])
    encabezado_obs.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_DORADO),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(encabezado_obs)

    cuerpo_obs = Table(
        [[Paragraph(
            observacion.texto if observacion else "Sin observaciones registradas.",
            estilo_observaciones
        )]],
        colWidths=[480]
    )
    cuerpo_obs.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MARRON),
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_DORADO_CLARO),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(cuerpo_obs)

    elementos.append(Spacer(1, 40))

    if FIRMA_DIRECTORA_PATH.exists():
        firma_directora_img = Image(str(FIRMA_DIRECTORA_PATH), width=110, height=55)
    else:
        firma_directora_img = Paragraph("_____________________________________", estilos["Normal"])

    firmas = [
        [
            firma_directora_img,
            Paragraph("_____________________________________", estilos["Normal"]),
        ],
        [
            Paragraph("FIRMA DIRECTORA", estilos["Normal"]),
            Paragraph("FIRMA PROFESOR (A)", estilos["Normal"]),
        ],
        [
            Paragraph(DIRECTOR_NOMBRE, estilos["Normal"]),
            Paragraph(docente_firma or "-", estilos["Normal"]),
        ],
    ]

    tabla_firmas = Table(firmas, colWidths=[240, 240], rowHeights=[60, None, None])
    tabla_firmas.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
    ]))

    elementos.append(tabla_firmas)

    documento.build(elementos)

    buffer.seek(0)

    nombre_archivo = f"boletin_{estudiante.id}_{periodo}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_archivo}"'
        }
    )


# ============================================================
# REPORTE DIARIO DE ASISTENCIA (PDF)
# ============================================================

@app.get("/reportes/asistencia-diaria/")
def reporte_asistencia_diaria(
    curso_id: int,
    fecha: date | None = None,
    db: Session = Depends(get_db)
):

    fecha_reporte = fecha or datetime.utcnow().date()

    curso = (
        db.query(models.Curso)
        .filter(models.Curso.id == curso_id)
        .first()
    )

    if not curso:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El curso no existe"
        )

    profesor = (
        db.query(models.Profesor)
        .filter(models.Profesor.id == curso.instructor_id)
        .first()
        if curso.instructor_id else None
    )

    asistencia_docente = None

    if profesor:

        asistencia_docente = (
            db.query(models.AsistenciaDocente)
            .filter(
                models.AsistenciaDocente.profesor_id == profesor.id,
                models.AsistenciaDocente.fecha == fecha_reporte
            )
            .first()
        )

    matriculas = (
        db.query(models.Matricula)
        .filter(models.Matricula.course_id == curso_id)
        .all()
    )

    estudiantes = sorted(
        (m.estudiante for m in matriculas if m.estudiante is not None),
        key=lambda e: e.nombre
    )

    registros = {
        r.student_id: r
        for r in db.query(models.Asistencia)
        .filter(
            models.Asistencia.course_id == curso_id,
            models.Asistencia.fecha == fecha_reporte
        )
        .all()
    }

    ESTADOS = {
        "presente": "Presente",
        "ausente": "Ausente",
        "tarde": "Tarde",
        "excusa": "Excusa",
    }

    buffer = io.BytesIO()

    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"Reporte de asistencia - {curso.title} - {fecha_reporte}",
        topMargin=36,
        bottomMargin=36
    )

    estilos = getSampleStyleSheet()
    elementos = []

    elementos.append(Paragraph("EduCampus · Colegio Manantial de Sabiduría (COLMAS)", estilos["Heading4"]))
    elementos.append(Paragraph(f"Asistencia — {curso.title} — {fecha_reporte.strftime('%d/%m/%Y')}", estilos["Title"]))
    elementos.append(Spacer(1, 10))

    if profesor:

        if asistencia_docente is None:
            estado_docente = "Sin registrar"
            color_estado = colors.grey
        elif not asistencia_docente.presente:
            estado_docente = "Ausente"
            color_estado = colors.HexColor("#C0392B")
        elif not asistencia_docente.completo:
            estado_docente = "Presente (incompleto)"
            color_estado = colors.HexColor("#E67E22")
        else:
            estado_docente = "Presente (completo)"
            color_estado = colors.HexColor("#27AE60")

        estilo_docente = ParagraphStyle(
            "DocenteNombre",
            parent=estilos["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11
        )

        estilo_estado = ParagraphStyle(
            "DocenteEstado",
            parent=estilos["Normal"],
            fontSize=10,
            textColor=color_estado,
            fontName="Helvetica-Bold"
        )

        encabezado_docente = Table(
            [[
                Paragraph(f"Docente: {profesor.nombre}", estilo_docente),
                Paragraph(estado_docente, estilo_estado),
            ]],
            colWidths=[340, 140]
        )
        encabezado_docente.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F7")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ]))

        elementos.append(encabezado_docente)
        elementos.append(Spacer(1, 16))

    if not estudiantes:

        elementos.append(Paragraph(
            "No hay estudiantes matriculados en este curso.",
            estilos["Normal"]
        ))

    else:

        filas = [["Estudiante", "Estado"]]

        for estudiante in estudiantes:

            registro = registros.get(estudiante.id)
            estado = ESTADOS.get(registro.status, "Sin registrar") if registro else "Sin registrar"

            filas.append([estudiante.nombre, estado])

        tabla_estudiantes = Table(filas, colWidths=[340, 140])
        tabla_estudiantes.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7E7EC")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        elementos.append(tabla_estudiantes)

    documento.build(elementos)

    buffer.seek(0)

    nombre_archivo = f"asistencia_{curso.title.replace(' ', '_')}_{fecha_reporte}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_archivo}"'
        }
    )


# ============================================================
# EVENTOS DE CALENDARIO
# ============================================================

@app.post(
    "/eventos-calendario/",
    response_model=schemas.EventoCalendarioResponse,
    status_code=status.HTTP_201_CREATED
)
def crear_evento_calendario(
    evento: schemas.EventoCalendarioCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(requerir_admin)
):

    nuevo_evento = models.EventoCalendario(
        titulo=evento.titulo.strip(),
        descripcion=evento.descripcion.strip(),
        fecha=evento.fecha,
        creado_por_id=admin["usuario_id"]
    )

    db.add(nuevo_evento)
    db.commit()
    db.refresh(nuevo_evento)

    return nuevo_evento


@app.get(
    "/eventos-calendario/",
    response_model=List[schemas.EventoCalendarioResponse]
)
def listar_eventos_calendario(
    db: Session = Depends(get_db),
    _sesion: dict = Depends(requerir_sesion)
):

    return (
        db.query(models.EventoCalendario)
        .order_by(models.EventoCalendario.fecha)
        .all()
    )


@app.delete(
    "/eventos-calendario/{evento_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_evento_calendario(
    evento_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(requerir_admin)
):

    existente = (
        db.query(models.EventoCalendario)
        .filter(models.EventoCalendario.id == evento_id)
        .first()
    )

    if not existente:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El evento no existe"
        )

    db.delete(existente)
    db.commit()


# ============================================================
# CLASES FINALIZADAS
# ============================================================

@app.get(
    "/clases-finalizadas/",
    response_model=List[schemas.ClaseFinalizadaResponse]
)
def listar_clases_finalizadas(
    db: Session = Depends(get_db)
):

    registros = (
        db.query(models.ClaseFinalizada)
        .order_by(models.ClaseFinalizada.fecha_hora.desc())
        .all()
    )

    resultado = []

    for r in registros:

        curso = r.curso
        profesor = curso.profesor if curso else None
        grado = curso.grado if curso else None

        resultado.append({
            "id": r.id,
            "docente_nombre": profesor.nombre if profesor else "Docente",
            "materia": curso.title if curso else "Curso",
            "grado": grado.nombre if grado else "",
            "observacion": r.observacion,
            "fecha_hora": r.fecha_hora,
        })

    return resultado
