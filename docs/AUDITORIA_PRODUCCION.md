# Auditoría: ¿está E-Pakty listo para un colegio real?

Actualizada el 2026-11-25. Verificado: 62 pruebas del backend, recorrido completo en local y sitio público desplegado.

## Cómo funciona de punta a punta
1. **Administración** entra con usuario y contraseña y sube los seis CSV (o los carga el sistema académico por API).
2. La **API** guarda el trabajo; el **worker** valida, separa los nombres a una bóveda con vencimiento (LOPDP), calcula, guarda en Supabase y **sube los datos al motor de Wilo** (sin nombres).
3. **Consumidores** (rectoría, tutor, DECE…) solo leen: semáforo de 4 colores, explicación SHAP, simulador «qué pasaría si», contexto territorial y los tableros del motor. El tutor ve solo su paralelo; ningún rol pedagógico ve datos financieros.
4. Los casos críticos abren una **intervención**; n8n pide un borrador a **Nova Lite**; **una persona lo edita y aprueba**; recién entonces se envía por correo.

## Estado de cada pieza
| Pieza | Estado |
|---|---|
| Inicio de sesión, roles, usuarios (crear, restablecer, desactivar) | **Listo**, también contra Supabase |
| Alerta temprana, SHAP, simulador, territorio | **Listo** (modelo de referencia, sin entrenar con retiros) |
| Motor de Wilo (7 redes PyTorch) | **Conectado y probado**: 240 procesados, 0 rechazados, roles y colegios aislados |
| Asistente de IA + aprobación humana + correo | **Listo y probado** en local; el correo sale por SMTP |
| Base de datos | **Supabase** con TLS; esquema y datos de prueba cargados |
| Sitio público (`epakti.vercel.app`) | **Desplegado**: `/health` 200; consulta resultados, usuarios y estado |
| Paquete de servidor (API, worker, n8n, proxy) | **Listo para subir**: `compose.yaml` + `docs/DESPLIEGUE_PRODUCCION.md` |

## Lo que falta, por quién
| Qué | Quién |
|---|---|
| Elegir y contratar el servidor, apuntar los DNS y ejecutar `docs/DESPLIEGUE_PRODUCCION.md` | Tú (todo el software ya está empaquetado) |
| Webhook de n8n en el motor (`N8N_WEBHOOK_URL`) | Wilo, cuando exista la dirección pública de n8n |
| Verificación de firma HMAC en el flujo `epakti-alerta-360` antes de exponerlo | Nosotros, al desplegar (hoy el flujo no valida y no debe publicarse) |
| Autenticación real con Supabase Auth hacia el motor (ES256) | Wilo + una fase posterior |
| Claves nuevas del motor (se compartieron por chat) | Wilo |
| Modelo entrenado y validado con **retiros reales** | Datos del colegio + Wilo |
| WhatsApp y dominio propio de correo (SPF/DKIM) | Pendiente por decisión del equipo |
| Datos reales: base legal y consentimiento (LOPDP); hoy la carga exige declarar datos sintéticos | Institución |
| Retirar las claves de AWS y las contraseñas de aplicación que se pegaron en el chat; borrar el flujo «ZZ copia sin usar» en n8n | Tú |

## Riesgos que conviene conocer
- Un puntaje alto es una **prioridad relativa** dentro del colegio, no la probabilidad de que alguien se retire. No usarlo para decidir becas, promoción ni retiro.
- La simulación es un escenario con supuestos explícitos, no un efecto causal medido; solo el seguimiento real confirma si una acción funcionó.
- NEE y efecto docente son hipótesis de diseño sin validar: no decidir acceso educativo con ellos.
- Las cuentas definidas en `PAKTAI_USERS` (variable del servidor) no se editan desde la pantalla; se recomienda crear las de uso diario desde **Usuarios**.

## Condición de salida a producción
Piloto controlado con un colegio, primero con datos sintéticos: carga → cálculo → caso → borrador → aprobación → entrega en sandbox, con RBAC, idempotencia
y auditoría verificados (los pasos de verificación están en `docs/DESPLIEGUE_PRODUCCION.md`, sección 5). Ver también `AUDITORIA_OPERACION_2026-11-25.md` y `CONECTAR_N8N_LOCAL.md`.
