# ADR-0089 · HTTP va por un solo manager, en el hilo de la interfaz, y reintenta

- **Estado:** Aceptada. El usuario eligió lo recomendado: un solo manager en el hilo principal, con
  las tareas bloqueando su hilo; los reintentos también con un servicio externo, y una descarga
  cortada que empieza de nuevo (2026-11-18)
- **Fecha:** 2026-11-18
- **Alcance:** `core/http.py`, `core/tasks/utils.py`, `main.py`

## Contexto

`qt.md` de canone pide un solo `QNetworkAccessManager`, que libera cada respuesta con
`setAutoDeleteReplies(True)`. La documentación de Qt dice lo mismo: «One QNetworkAccessManager
instance should be enough for the whole Qt application», y un manager solo se usa desde el hilo
al que pertenece. El [ADR-0079](0079-http-bloquea-el-hilo-de-la-tarea.md) creaba uno por petición,
en el hilo de la tarea, con un `QEventLoop` local.

`transversal.md` de canone, «Reintentos», pide reintentar también con un servicio externo
(ADR-0186 de canone). Las tareas de Consola hablan con Cloudflare, el índice de Flutter, la página de
Android Studio y los servicios de IP pública, y descargan los SDK.

## Decisión

1. `main.py` crea con `http.start()` el único manager, en el hilo de la interfaz. Llamar a
   `start()` dos veces es un `RuntimeError`.
2. `request` y `download` bloquean a quien llama: mandan la petición al hilo de la interfaz por una
   señal encolada y esperan las partes de la respuesta en una cola.
3. Una llamada desde el hilo del manager es un `RuntimeError`: esperaría una respuesta que ese mismo
   hilo tiene que recibir.
4. Ante un fallo de red, un 502, un 503 o un 504, una petición idempotente se reintenta hasta 3
   veces, con espera exponencial y jitter completo. Un `POST` no se reintenta. El vencimiento de
   `timeout` cuenta como fallo de red.
5. Un reintento empieza de cero: `download` recibe `on_restart`, que le dice a quien recibe las
   partes que descarte lo que tiene.
6. Un error que no se reintenta, o el último intento, levanta `OSError`, como antes.

## Consecuencias

- Las pruebas que llaman a `core/http.py` lo hacen desde un hilo, mientras el principal atiende al
  manager.
- Una descarga cortada se escribe de nuevo desde el principio; no se retoma donde quedó.
- `core/` sigue importando Qt en `core/http.py`, y ahora también una señal y un `QObject`, que no
  salen del módulo.

Reemplaza al ADR-0079.

## Descartado

- **Un manager por hilo de tarea:** pide una excepción en `qt.md` y se aparta de lo que recomienda
  Qt.
- **Reescribir las tareas con señales:** partiría cada tarea en callbacks para seguir esperando lo
  mismo.
- **Retomar la descarga con `Range`:** no todo servidor lo acepta, y no hay un síntoma que lo pida.
