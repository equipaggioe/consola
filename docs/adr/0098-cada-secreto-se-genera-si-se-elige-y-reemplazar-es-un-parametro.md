# ADR-0098 · Cada secreto se genera si se elige, y reemplazar los que tienen valor es un parámetro

- **Estado:** Aceptada
- **Fecha:** 2026-11-25
- **Alcance:** `services/tasks/vps_setup.py`, `services/canone.py`, `services/catalog.py`,
  `widgets/env_panel.py`

## Contexto

El `Settings` de la plantilla de canone pide secretos que son solo bytes al azar, cada uno en su
formato. El [ADR-0097](0097-los-secretos-vacios-se-generan-solo-si-se-elige.md) ofrecía generar solo los vacíos:
los demás no aparecían, y un secreto vacío en `config.env` que el VPS ya usaba se reemplazaba sin
aviso.

## Decisión

1. «Cargar credenciales» tiene un parámetro por cada secreto a generar, también los que ya tienen
   valor, y dice cuáles lo tienen.
2. Son `health_token`, `page_token_key`, `refresh_key` y `vapid_key`, si `Settings` los declara.
3. Otro parámetro, la casilla «Reemplazar», decide qué pasa con los que ya tienen valor: sin marcar,
   se generan solo los que no tienen; marcada, todos los elegidos. No se pide confirmación.
4. Un secreto que no se marca y está vacío corta la carga.
5. Sin «Reemplazar», uno vacío en `config.env` que el VPS ya tiene corta la carga.
6. Los generados se guardan en `config.env` justo antes de cargarlos, cuando ya se comprobó todo lo
   demás.
7. «Configurar VPS» no los genera.
8. Ni los marcados ni «Reemplazar» se guardan para la próxima corrida.

## Consecuencias

- Al reemplazar, el valor anterior se pierde en `config.env` y en el VPS: con otra `refresh_key` las
  apps vuelven a entrar, con otra `vapid_key` la web se vuelve a suscribir al push, con otro
  `health_token` hay que dárselo a quien vigila la salud, y con otra `page_token_key` una lista
  abierta se vuelve a pedir desde el principio.
- Marcar un secreto entra al VPS antes de generar: si no se entra, no cambia nada.

## Descartado

- **Dos opciones, «Conservar» y «Reemplazar»:** es un sí o un no, y va en una sola casilla.
- **Confirmar al ejecutar:** el parámetro ya lo dice, y la corrida no se detiene a preguntar.
- **Ofrecer solo los vacíos:** los demás parecían no existir.
- **Un botón aparte:** es un paso más antes del que los usa.
- **Un solo parámetro para todos:** no deja generar uno y escribir otro.
- **Generarlos siempre, como `SETUP_CODE`:** reemplazaría los del VPS sin que nadie lo eligiera.
- **Generar `equipaggio_key` o `restic_password`:** la primera la da Equipaggio, y con otra
  `restic_password` no se abren los respaldos que ya existen.
