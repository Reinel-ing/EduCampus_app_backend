import re
from datetime import datetime, date, time
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


CARACTER_ESPECIAL = re.compile(r"[!@#$%^&*()_+\-=\[\]{};:'\",.<>/?\\|`~]")


def validar_password_segura(v: str) -> str:
    if not any(c.isupper() for c in v):
        raise ValueError(
            "La contraseña debe tener al menos una letra mayúscula"
        )

    if not any(c.isdigit() for c in v):
        raise ValueError(
            "La contraseña debe tener al menos un número"
        )

    if not CARACTER_ESPECIAL.search(v):
        raise ValueError(
            "La contraseña debe tener al menos un carácter especial (ej. ! @ # $ % &)"
        )

    return v


# ============================================================
# USUARIOS
# ============================================================

class UsuarioCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    correo: EmailStr
    password: str = Field(min_length=6, max_length=100)
    rol: str = "estudiante"

    # Específicos de acudiente
    telefono: Optional[str] = None

    # Específicos de profesor/docente
    especialidad: Optional[str] = None

    # Específicos de estudiante
    grado_id: Optional[int] = None
    acudiente_id: Optional[int] = None

    @field_validator("correo")
    @classmethod
    def validar_gmail(cls, v: EmailStr) -> str:
        correo = str(v).lower().strip()

        if not correo.endswith("@gmail.com"):
            raise ValueError(
                "El correo debe pertenecer obligatoriamente al dominio @gmail.com"
            )

        return correo

    @field_validator("password")
    @classmethod
    def validar_password(cls, v: str) -> str:
        return validar_password_segura(v)

    @field_validator("rol")
    @classmethod
    def validar_rol(cls, v: str) -> str:
        roles_validos = {
            "estudiante",
            "profesor",
            "docente",
            "administrador",
            "acudiente",
        }

        v = v.lower().strip()

        if v not in roles_validos:
            raise ValueError(
                "El rol debe ser estudiante, profesor, docente, administrador o acudiente"
            )

        return v


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    correo: str
    rol: str


class RestablecerPasswordRequest(BaseModel):
    correo: EmailStr
    rol: str
    password: str = Field(min_length=6, max_length=100)

    @field_validator("password")
    @classmethod
    def validar_password(cls, v: str) -> str:
        return validar_password_segura(v)


class LoginRequest(BaseModel):
    correo: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    rol: str
    nombre: str
    usuario_id: int
    correo: str


# ============================================================
# GRADOS
# ============================================================

class GradoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    es_preescolar: bool = False
    director_grupo_id: Optional[int] = None


class GradoResponse(GradoCreate):
    id: int

    model_config = {
        "from_attributes": True
    }


# ============================================================
# ACUDIENTES
# ============================================================

class AcudienteCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    correo: EmailStr
    telefono: Optional[str] = None

    @field_validator("correo")
    @classmethod
    def validar_gmail(cls, v: EmailStr) -> str:
        correo = str(v).lower().strip()

        if not correo.endswith("@gmail.com"):
            raise ValueError(
                "El correo debe pertenecer obligatoriamente al dominio @gmail.com"
            )

        return correo


class AcudienteResponse(AcudienteCreate):
    id: int

    model_config = {
        "from_attributes": True
    }


# ============================================================
# ESTUDIANTES
# ============================================================

class EstudianteCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    correo: EmailStr
    grado_id: Optional[int] = None
    acudiente_id: Optional[int] = None

    @field_validator("correo")
    @classmethod
    def validar_gmail(cls, v: EmailStr) -> str:
        correo = str(v).lower().strip()

        if not correo.endswith("@gmail.com"):
            raise ValueError(
                "El correo debe pertenecer obligatoriamente al dominio @gmail.com"
            )

        return correo


class EstudianteResponse(EstudianteCreate):
    id: int

    model_config = {
        "from_attributes": True
    }


# ============================================================
# PROFESORES
# ============================================================

class ProfesorCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    correo: EmailStr
    especialidad: Optional[str] = None

    @field_validator("correo")
    @classmethod
    def validar_gmail(cls, v: EmailStr) -> str:
        correo = str(v).lower().strip()

        if not correo.endswith("@gmail.com"):
            raise ValueError(
                "El correo debe pertenecer obligatoriamente al dominio @gmail.com"
            )

        return correo


class ProfesorResponse(ProfesorCreate):
    id: int

    model_config = {
        "from_attributes": True
    }


# ============================================================
# CURSOS
# ============================================================

class CursoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None
    instructor_id: int
    grado_id: Optional[int] = None


# ============================================================
# MATRÍCULAS
# ============================================================

class MatriculaCreate(BaseModel):
    student_id: int
    course_id: int


# ============================================================
# CALIFICACIONES
# ============================================================

class CalificacionCreate(BaseModel):
    student_id: int
    course_id: int
    score: float = Field(ge=0, le=5)
    logro: Optional[str] = None
    periodo: str = "I"

    @field_validator("periodo")
    @classmethod
    def validar_periodo(cls, v: str) -> str:
        v = v.strip().upper()

        if v not in {"I", "II", "III", "IV"}:
            raise ValueError(
                "El periodo debe ser I, II, III o IV"
            )

        return v


# ============================================================
# OBSERVACIONES DEL BOLETÍN
# ============================================================

class ObservacionCreate(BaseModel):
    student_id: int
    periodo: str = "I"
    texto: str = Field(min_length=1)

    @field_validator("periodo")
    @classmethod
    def validar_periodo(cls, v: str) -> str:
        v = v.strip().upper()

        if v not in {"I", "II", "III", "IV"}:
            raise ValueError(
                "El periodo debe ser I, II, III o IV"
            )

        return v


class ObservacionResponse(ObservacionCreate):
    id: int

    model_config = {
        "from_attributes": True
    }


# ============================================================
# ASISTENCIAS
# ============================================================

class AsistenciaCreate(BaseModel):
    student_id: int
    course_id: int
    status: str
    fecha: Optional[date] = None


class AsistenciaResponse(BaseModel):
    id: int
    student_id: int
    course_id: int
    status: str
    fecha: date

    model_config = {
        "from_attributes": True
    }


# ============================================================
# ASISTENCIA DE DOCENTES
# ============================================================

class AsistenciaDocenteCreate(BaseModel):
    profesor_id: int
    fecha: Optional[date] = None
    presente: bool = True
    completo: bool = True
    observacion: Optional[str] = None


class AsistenciaDocenteResponse(BaseModel):
    id: int
    profesor_id: int
    fecha: date
    presente: bool
    completo: bool
    observacion: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


# ============================================================
# CONVIVENCIA
# ============================================================

class ConvivenciaCreate(BaseModel):
    student_id: int
    observacion: str
    tipo: str
    fecha: Optional[date] = None


# ============================================================
# ALERTAS
# ============================================================

class AlertaCreate(BaseModel):
    student_id: int
    mensaje: str
    severidad: str


# ============================================================
# NOTIFICACIONES
# ============================================================

class NotificacionResponse(BaseModel):
    id: int
    acudiente_id: int
    estudiante_id: Optional[int] = None
    titulo: str
    mensaje: str
    tipo: str
    leida: bool
    fecha: datetime

    model_config = {
        "from_attributes": True
    }


class AvisoRecogidaRequest(BaseModel):
    course_id: int


class AvisoRecogidaResponse(BaseModel):
    acudientes_notificados: int
    curso: str


# ============================================================
# MATERIAL DIDÁCTICO
# ============================================================

class MaterialCreate(BaseModel):
    curso_id: int
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = ""
    materia: str = ""
    enlace: str = ""
    archivo_nombre: Optional[str] = None
    archivo_base64: Optional[str] = None


class MaterialResponse(MaterialCreate):
    id: int
    fecha_creacion: datetime

    model_config = {
        "from_attributes": True
    }


# ============================================================
# TAREAS
# ============================================================

class TareaCreate(BaseModel):
    curso_id: int
    titulo: str
    descripcion: Optional[str] = None
    fecha_entrega: datetime
    permite_video: bool = False


# ============================================================
# ENTREGAS DE ACTIVIDADES
# ============================================================

class EntregaResponse(BaseModel):
    id: int
    tarea_id: int
    student_id: int
    acudiente_id: Optional[int] = None
    archivo_tipo: str
    nombre_original: str
    comentario: Optional[str] = None
    fecha_entrega: datetime

    model_config = {
        "from_attributes": True
    }


# ============================================================
# HORARIOS
# ============================================================

class HorarioCreate(BaseModel):
    curso_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time


# ============================================================
# COMUNICADOS
# ============================================================

class ComunicadoCreate(BaseModel):
    remitente: str
    titulo: str
    mensaje: str
    destinatario_rol: str
    fecha: Optional[datetime] = None


# ============================================================
# EVENTOS DE CALENDARIO
# ============================================================

class EventoCalendarioCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = ""
    fecha: date


class EventoCalendarioResponse(EventoCalendarioCreate):
    id: int

    model_config = {
        "from_attributes": True
    }