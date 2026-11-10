# ADR-0085 · `--turn` sale de que `Settings` declare `turn_secret`, no de una clave

- **Estado:** Aceptada
- **Fecha:** 2026-11-10
- **Alcance:** core/canone.py, core/settings.py, core/fields.py, core/catalog.py, ui/env_panel.py

Modifica el punto 6 del [ADR-0066](0066-configurar-vps-prepara-la-maquina-y-corre-install-py.md): coturn ya no se instala «con `TURN`».

## Contexto

`TURN` era un sí/no de `config.env` que decidía `install.py --turn` y el paquete `coturn`. Que la app tenga llamadas ya lo dice su código: un servidor con llamadas lee `turn_secret`, que `install.py` escribe solo con `--turn`, y canone exige todos los campos de `Settings`. Eran dos fuentes del mismo dato, y podían contradecirse. Además, «Llamadas con coturn» aparecía en todos los repos, tuvieran llamadas o no.

## Decisión

1. **Sale la clave `TURN`.** `canone.calls` devuelve si `<SERVER_DIR>/src/app/config.py` declara `turn_secret`. Con eso van `--turn` de `install.py` y de `packages.py`.
2. **Una clave que solo aplica a un repo con cierto campo lo declara en `Setting.needs`.** El formulario de Configuración del repo no la muestra si `Settings` no declara ese campo, salvo que ya tenga un valor. Hoy solo `TURN_IP`, con `turn_secret`.
3. **`TURN_IP` en un repo sin `turn_secret` corta** «Configurar VPS», nombrando la clave que hay que borrar.

## Consecuencias

- El mismo método sirve para otra opción de `install.py` si el repo ya la delata en su código, como pasa con `--desktop` (el `release.yml`) y `--without` (las carpetas). `--extension` y `--allow` no tienen esa señal hoy: para derivarlos, canone tendría que fijar dónde la declara el repo.

## Descartado

- **Ocultar `TURN` y `TURN_IP` en un repo sin `turn_secret`, y conservar la clave.** Seguían siendo dos fuentes: un repo con `turn_secret` y `TURN=no` instalaba un servidor que no arranca.
