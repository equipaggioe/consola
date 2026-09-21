# ADR-0030 · Se cachea lo que una herramienta publica, nunca lo que cambia solo

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/cache.py, core/catalog.py, core/android.py

## Contexto

`avdmanager list device` y `sdkmanager --list` tardan de segundos a decenas de segundos, y el panel los necesita cada vez que se dibuja: preguntárselos al SDK en cada apertura de pestaña congelaría la interfaz por algo que no cambia en meses. Pero la misma caché aplicada a qué AVD existen o qué emulador está vivo haría que la interfaz mienta.

## Decisión

1. Se cachea el **catálogo** —lo que una herramienta publica: qué dispositivos existen, qué imágenes se pueden bajar— con un mes de vida por defecto.
2. Lo que cambia mientras la aplicación está abierta —imágenes instaladas, AVD creados, servicios del VPS— se cachea **60 segundos**: alcanza para no repetir la consulta al abrir tres pestañas seguidas, y no alcanza para mentir después de una instalación.
3. Lo que es **estado** no se cachea nunca: qué emuladores están vivos se pregunta siempre.
4. La caché del VPS lleva el **host en la clave**: dos repos abiertos son casi siempre dos VPS, y compartir la respuesta le mostraría a uno los servicios del otro.
5. Vive fuera de los repos, en la carpeta de datos de la máquina: es historia de la máquina.
6. Una caché ilegible es una caché vacía, nunca un error que corte una tarea.
7. Al terminar una tarea de máquina se olvida lo que esa tarea pudo haber cambiado.

## Consecuencias

- El panel del emulador abre rápido después de la primera vez.
- Hay dos caminos de refresco: el normal, que respeta la caché y corre al mostrar la pestaña, y el forzado, que la saltea.
- Decidir bien entre catálogo y estado es la parte que se puede equivocar, y el síntoma es una lista que ofrece algo que ya no existe.

## Descartado

- **Cachear también el estado.** Ofrecería apagar un emulador que ya no está.
- **No cachear nada.** Congela la interfaz por decenas de segundos cada vez que se abre una pestaña del grupo.
