# ADR-0097 · Los secretos vacíos se generan solo si se elige al cargar las credenciales

- **Estado:** Aceptada. El punto marcado *(propuesta)* no está confirmado.
- **Fecha:** 2026-11-25
- **Alcance:** `services/tasks/vps_setup.py`, `services/catalog.py`

## Contexto

El `Settings` de la plantilla de canone pide secretos que son solo bytes al azar, cada uno en su
formato, y había que crearlos a mano. `setup_code` ya se genera al cargarlo si está vacío.

## Decisión

1. «Cargar credenciales» tiene un parámetro que genera los secretos vacíos y los guarda en
   `config.env`. *(propuesta)*
2. Por defecto los exige, y corta si falta uno.
3. Son `health_token`, `page_token_key`, `refresh_key` y `vapid_key`, si `Settings` los declara.
4. «Configurar VPS» no los genera.

## Consecuencias

- Con `config.env` perdido, generar reemplaza los del VPS: con otra `refresh_key` las apps vuelven a
  entrar, con otra `vapid_key` la web se vuelve a suscribir al push, y con otro `health_token` hay
  que dárselo de nuevo a quien vigila la salud.

## Descartado

- **Un botón aparte:** es un paso más antes del que los usa.
- **Generarlos siempre, como `SETUP_CODE`:** reemplazaría los del VPS sin que nadie lo eligiera.
- **Generar `equipaggio_key` o `restic_password`:** la primera la da Equipaggio, y con otra
  `restic_password` no se abren los respaldos que ya existen.
