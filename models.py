from datetime import datetime, date, time

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    Date,
    Time,
    ForeignKey,
    UniqueConstraint,
)

from sqlalchemy.orm import relationship

from database import Base


# ============================================================
# ADMINISTRADORES
# ============================================================

class Administrador(Base):
    __tablename__ = "administradores"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    correo = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============================================================
# GRADOS
# ============================================================

class Grado(Base):
    __tablename__ = "grados"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)

    es_preescolar = Column(Boolean, default=False, nullable=False)

    director_grupo_id = Column(
        Integer,
        ForeignKey("profesores.id", ondelete="SET NULL"),
        nullable=True
    )

    estudiantes = relationship(
        "Estudiante",
        back_populates="grado"
    )

    cursos = relationship(
        "Curso",
        back_populates="grado"
    )

    director_grupo = relationship("Profesor")


# ============================================================
# ACUDIENTES
# ============================================================

class Acudiente(Base):
    __tablename__ = "acudientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    correo = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=True)
    telefono = Column(String(30), nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    estudiantes = relationship(
        "Estudiante",
        back_populates="acudiente"
    )


# ============================================================
# ESTUDIANTES
# ============================================================

class Estudiante(Base):
    __tablename__ = "estudiantes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    correo = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    grado_id = Column(
        Integer,
        ForeignKey("grados.id", ondelete="SET NULL"),
        nullable=True
    )

    acudiente_id = Column(
        Integer,
        ForeignKey("acudientes.id", ondelete="SET NULL"),
        nullable=True
    )

    grado = relationship(
        "Grado",
        back_populates="estudiantes"
    )

    acudiente = relationship(
        "Acudiente",
        back_populates="estudiantes"
    )

    matriculas = relationship(
        "Matricula",
        back_populates="estudiante",
        cascade="all, delete-orphan"
    )

    calificaciones = relationship(
        "Calificacion",
        back_populates="estudiante",
        cascade="all, delete-orphan"
    )

    asistencias = relationship(
        "Asistencia",
        back_populates="estudiante",
        cascade="all, delete-orphan"
    )

    convivencias = relationship(
        "Convivencia",
        back_populates="estudiante",
        cascade="all, delete-orphan"
    )

    alertas = relationship(
        "AlertaAlumno",
        back_populates="estudiante",
        cascade="all, delete-orphan"
    )


# ============================================================
# PROFESORES
# ============================================================

class Profesor(Base):
    __tablename__ = "profesores"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    correo = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=True)
    especialidad = Column(String(150), nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    cursos = relationship(
        "Curso",
        back_populates="profesor"
    )


# ============================================================
# CURSOS
# ============================================================

class Curso(Base):
    __tablename__ = "cursos"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(
        String(150),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    instructor_id = Column(
        Integer,
        ForeignKey("profesores.id", ondelete="RESTRICT"),
        nullable=False
    )

    grado_id = Column(
        Integer,
        ForeignKey("grados.id", ondelete="SET NULL"),
        nullable=True
    )

    profesor = relationship(
        "Profesor",
        back_populates="cursos"
    )

    grado = relationship(
        "Grado",
        back_populates="cursos"
    )

    matriculas = relationship(
        "Matricula",
        back_populates="curso",
        cascade="all, delete-orphan"
    )

    calificaciones = relationship(
        "Calificacion",
        back_populates="curso",
        cascade="all, delete-orphan"
    )

    asistencias = relationship(
        "Asistencia",
        back_populates="curso",
        cascade="all, delete-orphan"
    )

    materiales = relationship(
        "MaterialDidactico",
        back_populates="curso",
        cascade="all, delete-orphan"
    )

    tareas = relationship(
        "Tarea",
        back_populates="curso",
        cascade="all, delete-orphan"
    )

    horarios = relationship(
        "Horario",
        back_populates="curso",
        cascade="all, delete-orphan"
    )


# ============================================================
# MATRÍCULAS
# ============================================================

class Matricula(Base):
    __tablename__ = "matriculas"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="CASCADE"),
        nullable=False
    )

    course_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    fecha_matricula = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    estudiante = relationship(
        "Estudiante",
        back_populates="matriculas"
    )

    curso = relationship(
        "Curso",
        back_populates="matriculas"
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            name="uq_matricula_estudiante_curso"
        ),
    )


# ============================================================
# CALIFICACIONES
# ============================================================

class Calificacion(Base):
    __tablename__ = "calificaciones"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="CASCADE"),
        nullable=False
    )

    course_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    periodo = Column(
        String(10),
        nullable=False,
        default="I",
        server_default="I"
    )

    score = Column(Float, nullable=False)

    logro = Column(
        Text,
        nullable=True
    )

    fecha = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    estudiante = relationship(
        "Estudiante",
        back_populates="calificaciones"
    )

    curso = relationship(
        "Curso",
        back_populates="calificaciones"
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            "periodo",
            name="uq_calificacion_estudiante_curso_periodo"
        ),
    )


# ============================================================
# OBSERVACIONES DEL BOLETÍN
# ============================================================

class Observacion(Base):
    __tablename__ = "observaciones_boletin"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="CASCADE"),
        nullable=False
    )

    periodo = Column(String(10), nullable=False, default="I")

    texto = Column(Text, nullable=False)

    fecha = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    estudiante = relationship("Estudiante")

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "periodo",
            name="uq_observacion_estudiante_periodo"
        ),
    )


# ============================================================
# ASISTENCIAS
# ============================================================

class Asistencia(Base):
    __tablename__ = "asistencias"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="CASCADE"),
        nullable=False
    )

    course_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    status = Column(
        String(30),
        nullable=False
    )

    fecha = Column(
        Date,
        default=date.today,
        nullable=False
    )

    estudiante = relationship(
        "Estudiante",
        back_populates="asistencias"
    )

    curso = relationship(
        "Curso",
        back_populates="asistencias"
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            "fecha",
            name="uq_asistencia_estudiante_curso_fecha"
        ),
    )


# ============================================================
# ASISTENCIA DE DOCENTES
# ============================================================

class AsistenciaDocente(Base):
    __tablename__ = "asistencias_docentes"

    id = Column(Integer, primary_key=True, index=True)

    profesor_id = Column(
        Integer,
        ForeignKey("profesores.id", ondelete="CASCADE"),
        nullable=False
    )

    fecha = Column(
        Date,
        default=date.today,
        nullable=False
    )

    presente = Column(Boolean, default=True, nullable=False)

    completo = Column(Boolean, default=True, nullable=False)

    observacion = Column(Text, nullable=True)

    profesor = relationship("Profesor")

    __table_args__ = (
        UniqueConstraint(
            "profesor_id",
            "fecha",
            name="uq_asistencia_docente_fecha"
        ),
    )


# ============================================================
# CONVIVENCIA
# ============================================================

class Convivencia(Base):
    __tablename__ = "convivencia"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="CASCADE"),
        nullable=False
    )

    titulo = Column(
        String(200),
        nullable=False,
        default="",
        server_default=""
    )

    observacion = Column(
        Text,
        nullable=False
    )

    tipo = Column(
        String(50),
        nullable=False
    )

    fecha = Column(
        Date,
        default=date.today,
        nullable=False
    )

    seguimiento_realizado = Column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false"
    )

    nota_seguimiento = Column(Text, nullable=True)

    estudiante = relationship(
        "Estudiante",
        back_populates="convivencias"
    )


# ============================================================
# ALERTAS
# ============================================================

class AlertaAlumno(Base):
    __tablename__ = "alertas_alumnos"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="CASCADE"),
        nullable=False
    )

    docente_nombre = Column(
        String(150),
        nullable=False,
        default="",
        server_default=""
    )

    mensaje = Column(
        Text,
        nullable=False
    )

    severidad = Column(
        String(30),
        nullable=False
    )

    atendida = Column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false"
    )

    respuesta_admin = Column(Text, nullable=True)

    fecha = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    estudiante = relationship(
        "Estudiante",
        back_populates="alertas"
    )


# ============================================================
# NOTIFICACIONES (acudientes)
# ============================================================

class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)

    acudiente_id = Column(
        Integer,
        ForeignKey("acudientes.id", ondelete="CASCADE"),
        nullable=True
    )

    profesor_id = Column(
        Integer,
        ForeignKey("profesores.id", ondelete="CASCADE"),
        nullable=True
    )

    estudiante_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="SET NULL"),
        nullable=True
    )

    titulo = Column(String(200), nullable=False)

    mensaje = Column(Text, nullable=False)

    tipo = Column(String(30), nullable=False, default="general")

    leida = Column(Boolean, default=False, nullable=False)

    fecha = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    acudiente = relationship("Acudiente")
    estudiante = relationship("Estudiante")


# ============================================================
# MATERIAL DIDÁCTICO
# ============================================================

class MaterialDidactico(Base):
    __tablename__ = "materiales_didacticos"

    id = Column(Integer, primary_key=True, index=True)

    curso_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    titulo = Column(
        String(200),
        nullable=False
    )

    descripcion = Column(Text, nullable=False, default="")
    materia = Column(String(150), nullable=False, default="")
    enlace = Column(String(500), nullable=False, default="")
    archivo_nombre = Column(String(255), nullable=True)
    archivo_base64 = Column(Text, nullable=True)

    archivo_url = Column(
        Text,
        nullable=True
    )

    fecha_creacion = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    curso = relationship(
        "Curso",
        back_populates="materiales"
    )


# ============================================================
# TAREAS
# ============================================================

class Tarea(Base):
    __tablename__ = "tareas"

    id = Column(Integer, primary_key=True, index=True)

    curso_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    titulo = Column(
        String(200),
        nullable=False
    )

    descripcion = Column(
        Text,
        nullable=True
    )

    fecha_entrega = Column(
        DateTime,
        nullable=False
    )

    permite_video = Column(
        Boolean,
        default=False,
        nullable=False
    )

    fecha_creacion = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    curso = relationship(
        "Curso",
        back_populates="tareas"
    )

    entregas = relationship(
        "TareaEntrega",
        back_populates="tarea",
        cascade="all, delete-orphan"
    )


# ============================================================
# ENTREGAS DE ACTIVIDADES
# ============================================================

class TareaEntrega(Base):
    __tablename__ = "tareas_entregas"

    id = Column(Integer, primary_key=True, index=True)

    tarea_id = Column(
        Integer,
        ForeignKey("tareas.id", ondelete="CASCADE"),
        nullable=False
    )

    student_id = Column(
        Integer,
        ForeignKey("estudiantes.id", ondelete="CASCADE"),
        nullable=False
    )

    acudiente_id = Column(
        Integer,
        ForeignKey("acudientes.id", ondelete="SET NULL"),
        nullable=True
    )

    archivo_path = Column(Text, nullable=False)

    archivo_tipo = Column(String(30), nullable=False)

    nombre_original = Column(String(255), nullable=False)

    comentario = Column(Text, nullable=True)

    nota = Column(Float, nullable=True)
    retroalimentacion = Column(Text, nullable=True)

    fecha_entrega = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    tarea = relationship(
        "Tarea",
        back_populates="entregas"
    )

    estudiante = relationship("Estudiante")

    acudiente = relationship("Acudiente")

    __table_args__ = (
        UniqueConstraint(
            "tarea_id",
            "student_id",
            name="uq_entrega_tarea_estudiante"
        ),
    )


# ============================================================
# HORARIOS
# ============================================================

class Horario(Base):
    __tablename__ = "horarios"

    id = Column(Integer, primary_key=True, index=True)

    curso_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    dia_semana = Column(
        String(20),
        nullable=False
    )

    hora_inicio = Column(
        Time,
        nullable=False
    )

    hora_fin = Column(
        Time,
        nullable=False
    )

    curso = relationship(
        "Curso",
        back_populates="horarios"
    )


# ============================================================
# COMUNICADOS
# ============================================================

class Comunicado(Base):
    __tablename__ = "comunicados"

    id = Column(Integer, primary_key=True, index=True)

    remitente = Column(
        String(150),
        nullable=False
    )

    titulo = Column(
        String(200),
        nullable=False
    )

    mensaje = Column(
        Text,
        nullable=False
    )

    destinatario_rol = Column(
        String(50),
        nullable=False
    )

    fecha = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )


# ============================================================
# EVENTOS DE CALENDARIO
# ============================================================

class EventoCalendario(Base):
    __tablename__ = "eventos_calendario"

    id = Column(Integer, primary_key=True, index=True)

    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=False, default="")
    fecha = Column(Date, nullable=False)

    creado_por_id = Column(
        Integer,
        ForeignKey("administradores.id", ondelete="SET NULL"),
        nullable=True
    )

    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============================================================
# CLASES FINALIZADAS (registro de "Ya pueden recoger")
# ============================================================

class ClaseFinalizada(Base):
    __tablename__ = "clases_finalizadas"

    id = Column(Integer, primary_key=True, index=True)

    curso_id = Column(
        Integer,
        ForeignKey("cursos.id", ondelete="CASCADE"),
        nullable=False
    )

    observacion = Column(Text, nullable=False, default="")
    fecha_hora = Column(DateTime, default=datetime.utcnow, nullable=False)

    curso = relationship("Curso")