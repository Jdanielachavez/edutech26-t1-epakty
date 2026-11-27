# Paso 4.3 · Reintento tras el fallo — SCH-PRUEBA-EQUIPO

Wilo: retomé desde el reintento con la URL nueva del motor. Esto es lo que salió.

## Resultado

| Dato | Valor |
|---|---|
| `job_id` del reintento | `LOAD-75AB77F1` |
| Estado final | `COMPLETED` |
| Estudiantes procesados | **241** |
| Estudiantes rechazados | **0** |
| Total en el triage (sin filtros) | **241** |
| `EST-241` en el triage | sí |
| `GET /students/EST-241/ficha-360` | `200` |
| Motor | `v2.4.0-tabm-mini-film-live`, `/health` → `200` |

El identificador de intento fue nuevo (`LOAD-…`, distinto a los de las cargas
anteriores), tal como pediste. El motor volvió a procesar los seis CSV y no
reutilizó el trabajo previo.

## Cómo se hizo

Se subieron los seis CSV de la segunda versión (la que incluye `EST-241`) con
`POST /ingestion/upload-csv` en multipart, usando el mismo cliente y la misma
función del portal (`backend/production/worker.py::push_to_engine`), que es el
código que corre cuando alguien sube los archivos desde la pantalla de carga.
No se usó una ruta alternativa ni una imitación del cliente.

Se ejecutó desde la máquina de Daniela, no desde el portal en producción,
porque producción todavía apuntaba a la URL anterior del túnel. La petición que
recibió el motor es idéntica a la que envía el portal.

## Lo que ya se había comprobado antes (sigue en pie)

- Carga inicial: 240 procesados, 0 rechazados.
- Actualización: 241 procesados, 0 rechazados, con `EST-241` visible.
- `estudiantes.csv` sin la columna `codigo`: el motor aceptó con `202`, terminó
  en `FAILED` con un mensaje claro sobre la columna faltante, y el panel
  conservó los 241 de la última carga válida.

## Una observación sobre el reintento

Cuando se reintenta desde el portal **con los seis archivos idénticos**, el
portal no vuelve a enviar la carga: calcula un identificador a partir del
contenido de los archivos y devuelve el trabajo anterior ya completado
(`nuevo: false`). Es decir, la deduplicación ocurre **antes** de llegar al
motor, no en el motor.

Para esta prueba eso significa que el reintento con un identificador nuevo, como
pediste, hay que forzarlo; desde la pantalla no sale solo si los archivos no
cambiaron. Dinos si prefieres que un reintento después de un `FAILED` siempre
vuelva a procesar aunque el contenido sea el mismo: es un cambio pequeño de
nuestro lado y nos parece razonable, porque un fallo del motor no se arregla
repitiendo el mismo identificador.

## Pendiente de nuestro lado

Producción (`epakti.vercel.app`) se apunta a la URL nueva con un comando; es lo
siguiente que hacemos. Mientras tanto, lo de arriba se verificó contra tu motor
en vivo, no contra un simulador.

## Una petición

El túnel rápido de Cloudflare cambia de dirección cada vez que reinicias la PC,
y cada cambio nos obliga a tocar producción. Si puedes dejar un túnel con nombre
fijo (o cualquier dirección estable), nos ahorramos ese paso en cada prueba.
