# ADR-0039 · Nada se sobrescribe a ciegas: primero se muestra qué va a cambiar

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/files.py, core/vps.py, core/tasks/utils.py, core/tasks/builders.py

## Contexto

Varias acciones pisan algo que ya está: una carpeta publicada, un archivo compartido en otro repo, la configuración de un servicio del VPS, el `.env` de la aplicación. Escribir primero y avisar después no deja ninguna oportunidad de notar que el destino no era el que uno creía.

## Decisión

1. Antes de escribir se **compara** contra lo que hay: `files.compare` devuelve `NEW`, `DIFF` o `SAME`, y `vps.write_config` imprime un `diff` unificado.
2. Lo que ya es idéntico **no se escribe**, y `write_config` lo dice en el log. Ese booleano es además lo que decide si hace falta reiniciar el servicio.
3. Las acciones que tocan varias cosas tienen un modo **simulacro**, que es su valor por defecto: lista lo que haría y no toca nada (`clean_artifacts`, `sync_common_files`, `sync_server_env`, `purge_emulators`).
4. Un simulacro no dispara el seguro de los destructivos, porque no destruye ([ADR-0018](0018-seguro-por-repo-y-objetivo.md)).
5. Lo que se va a borrar se enumera antes de pedir confirmación, con su tamaño cuando lo tiene.

## Consecuencias

- Cada destructivo tiene dos caminos —simulacro y aplicar— y los dos tienen que calcular exactamente la misma lista.
- Reconfigurar un servicio que no cambió no lo reinicia, lo que en Caddy evita cortar el 80 y el 443 de todo el VPS.

## Descartado

- **Escribir y avisar después.** No deja momento para notar que el destino no era el que uno creía.
