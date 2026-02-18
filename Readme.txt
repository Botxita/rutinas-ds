# Rutinas DS — Especificación Funcional (v1)

## Descripción general
Rutinas DS es un sistema de gestión de rutinas de entrenamiento para gimnasios, con acceso por QR y roles diferenciados.  
Permite asignar rutinas, editarlas, registrar ejecuciones, medir progreso y auditar el trabajo del staff.

La aplicación distingue claramente entre:
- **Rutinas base** (plantillas)
- **Rutinas asignadas** (copias editables por cliente)

---

## Roles del sistema

El sistema cuenta con **4 tipos de usuarios**:

- CLIENTE
- ENTRENADOR
- COORDINADOR
- ADMINISTRADOR

---

## Login

- **CLIENTE**: ingresa solo con DNI
- **ENTRENADOR / COORDINADOR / ADMINISTRADOR**: ingresan con DNI + clave

---

## Permisos por rol

### 1) CLIENTE

**Puede:**
- Iniciar sesión con DNI
- Ver su rutina activa:
  - completa
  - por día (Día 1, Día 2, etc.)
- Marcar la rutina como ejecutada
- Ver su progreso:
  - entrenamientos realizados
  - adherencia / rachas
- Cargar mediciones propias:
  - peso
  - perímetros (opcional)
  - notas
- Ver evolución de sus mediciones (historial / gráficos)
- Cerrar sesión

**No puede:**
- Editar rutinas
- Asignar rutinas
- Dar de baja clientes
- Ver auditorías
- Gestionar usuarios

---

### 2) ENTRENADOR

**Puede:**
- Iniciar sesión con DNI + clave
- Dar de alta clientes (DNI único)
- Dar de baja clientes
- Ver listado y detalle de clientes
- Asignar rutina base a un cliente
- Ver rutina activa de clientes
- Editar rutina asignada de clientes:
  - ejercicios
  - series
  - repeticiones
  - peso
  - descanso
  - notas
  - activar / desactivar ítems
- Marcar rutina como ejecutada (por cliente)
- Ver progreso de clientes
- Cargar y editar mediciones de clientes
- Ver evolución de mediciones de clientes
- Cerrar sesión

**No puede:**
- Ver auditorías o métricas de entrenadores
- Sincronizar rutinas base
- Gestionar usuarios staff

---

### 3) COORDINADOR

**Puede:**
- Iniciar sesión con DNI + clave
- Todo lo que puede un ENTRENADOR
- Ver auditorías y métricas:
  - actividad de entrenadores
  - altas de clientes
  - asignaciones y ediciones de rutinas
- Gestionar ENTRENADORES:
  - alta
  - baja
  - activar / desactivar
  - resetear clave
- Ver progreso y mediciones de clientes
- Dar de baja clientes
- Sincronizar rutinas base desde Google Sheets (manual)
- Cerrar sesión

**No puede:**
- Crear, editar o eliminar COORDINADORES
- Crear, editar o eliminar ADMINISTRADORES

---

### 4) ADMINISTRADOR

**Puede:**
- Iniciar sesión con DNI + clave
- Todo lo que puede un COORDINADOR
- Gestionar COORDINADORES:
  - alta
  - baja
  - activar / desactivar
  - resetear clave
- Gestionar ADMINISTRADORES
- Configuración global del sistema
- Acceso completo a logs y auditoría
- Dar de baja clientes
- Cerrar sesión

---

## Progreso e informes

- Todos los usuarios tienen acceso a informes de progreso:
  - CLIENTE: solo sus propios datos
  - ENTRENADOR: progreso de clientes
  - COORDINADOR / ADMIN: progreso de clientes + auditoría de entrenadores

El progreso incluye:
- Ejecuciones de entrenamientos
- Adherencia y rachas
- Evolución de cargas (si aplica)
- Mediciones voluntarias

---

## Mediciones

Las mediciones son **optativas** y se cargan libremente.

- CLIENTE: puede cargar, editar y ver sus mediciones
- ENTRENADOR: puede cargar y editar mediciones de clientes
- COORDINADOR / ADMIN: acceso completo

Mediciones típicas:
- Peso
- Perímetros
- Notas
- Evolución histórica y gráficos

---

## Rutinas

### Rutinas base
- Se editan únicamente en Google Sheets
- Funcionan como plantillas
- No se editan desde la app
- Se sincronizan manualmente por COORDINADOR o ADMINISTRADOR

### Rutinas asignadas
- Se generan al asignar una rutina base a un cliente
- Son copias independientes (snapshot)
- Se editan únicamente desde la app
- El cliente siempre ve su rutina asignada activa

---

## Baja de clientes

- Puede ser realizada por:
  - ENTRENADOR
  - COORDINADOR
  - ADMINISTRADOR
- El cliente nunca puede darse de baja a sí mismo
- La baja es lógica (inactivo), no se eliminan datos

---

## Notas finales

- La planilla de Google Sheets no es el motor operativo del sistema
- La base de datos operativa es la aplicación (backend)
- La interfaz gráfica debe respetar estrictamente los permisos definidos en este documento

---

Ejecución de rutina (cliente)

- 
“Marcar rutina ejecutada” refiere a marcar como completada la rutina del día (Día 1/Día 2/etc.) correspondiente.

- 
El cliente puede marcar más de una rutina como completada en un mismo día calendario, para registrar rutinas realizadas en días anteriores que no fueron marcadas en su momento (backfill).
- 

Cada marca de completado debe registrar fecha/hora de registro y el día de rutina (Día N).



Alta de cliente
- 

El alta de cliente requiere DNI (único), Nombre y Apellido.

- Validación: no puede existir más de un cliente con el mismo DNI.



Mediciones (cliente)
- 

El cliente puede cargar mediciones (peso/perímetros/notas) y editar esa misma medición (los datos asociados a la fecha en que se cargó).
- 

El historial se conserva para visualizar la evolución.

**Estado del documento:**  
Aprobado – Versión inicial (v1)
