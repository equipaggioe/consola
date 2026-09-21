# ADR-0022 · Instalar un paquete y configurar su servicio son dos acciones distintas

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/vps.py, core/tasks/vps_setup.py

## Contexto

«Instalar coturn» corría su propio `apt-get install` además de escribir la configuración, y eso ya lo hacía «Software base» con el grupo marcado. Era el único lugar del catálogo donde la misma acción vivía en dos botones.

## Decisión

1. **Instalar** es `install_base_software`, con un grupo de paquetes por casilla.
2. **Configurar** es su propio botón, y **no instala**: `vps.require_package` corta con «Corre "Software base" con el grupo X marcado».
3. Es la misma relación que ya tenían `postgresql` y `bootstrap_db`: el paquete se instala una vez, la configuración se repite.
4. Marcar un grupo y no configurarlo deja el servicio inerte, que es un estado legítimo — no uno roto.

## Consecuencias

- Cambiar el realm de coturn o una ruta de Caddy no vuelve a pasar por apt.
- Hay que correr dos botones en un servidor nuevo, y el segundo lo dice con esas palabras si falta el primero.
- La comprobación vive en `core/vps.py` y no en el módulo donde nació, porque la comparten los tres botones de configurar y uno está en otro módulo.

## Descartado

- **Que cada botón de configurar instale lo suyo.** Duplica la instalación y la esconde detrás de un nombre que no la anuncia.
