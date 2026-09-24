# 19 · Imágenes

El grupo **Imágenes** produce el material gráfico de las apps de un repo. Hoy tiene las capturas publicables; `generate_icons` está declarado sin cuerpo ([30](30_riesgos_y_pendientes.md)).

## 1. El corte: el repo pone la cámara, Consola el revelado

| Parte | Quién | Dónde |
|---|---|---|
| Sembrar datos ficticios, entrar sin login, navegar, sacar el PNG | el script del repo | lo que declara `SHOTS_CMD` |
| Elegir apps, temas, idiomas y emulador; encender el emulador | Consola | `core/tasks/images.py::shoot_screens` |
| Validar lo que dejó la cámara | Consola | `core/shots.py::collect`, `missing_combinations` |
| Convertir cada crudo para cada destino | Consola | `core/shots.py::render_landing`, `core/shots_presets.json` |

La cámara es código del repo porque solo el repo sabe navegar su app ([ADR-0049](../adr/0049-la-camara-de-capturas-es-un-script-del-repo.md)).

## 2. Los botones

| Botón | Qué hace |
|---|---|
| `shoot_screens` · Sacar capturas | Corre la cámara y comprueba lo que dejó |
| `render_shots` · Revelar capturas | Convierte los crudos para cada destino marcado |
| `screenshots` · Capturar y publicar | Compuesta: los dos anteriores, cada uno desmarcable |

Ejes de `shoot_screens` (y del paso `shoot` de la compuesta):

| Eje | Valores | Argumento |
|---|---|---|
| `apps` | descubiertos: SPA Vite y apps móviles (`shots.SHOT_KINDS`) | `--apps` |
| `themes` | `claro`, `oscuro` | `--themes` |
| `languages` | los de `SHOTS_LANGS` (fuente consultada `SHOTS_LANGUAGES`, sin caché) | `--languages` |
| `avd` | AVD creados; vacío solo vale sin apps móviles marcadas | `--device` con el serial |

Eje de `render_shots` y de la compuesta: `destinations`. Solo `landing` tiene preset; marcar otro corta la corrida antes de convertir nada.

## 3. La corrida de la cámara

1. Si hay una app móvil marcada y no se eligió AVD, corta antes de empezar.
2. Borra de `SHOTS_RAW` los crudos de las combinaciones pedidas (`clear_raw`): una pantalla que el script dejó de sacar no sobrevive a la corrida siguiente. Las combinaciones no pedidas no se tocan.
3. Con app móvil: si el AVD ya está encendido, usa su serial; si no, lo enciende en un hilo aparte con un puerto elegido de antemano, espera el arranque, y lo apaga por adb al terminar. De su salida solo pasan al log los avisos y los errores.
4. Corre `SHOTS_CMD` desde la raíz del repo con los argumentos de §2 y `--output` con `SHOTS_RAW` absoluta. El primer token se resuelve en el PATH; el resto va tal cual.
5. Lee los crudos de las apps pedidas y corta si un archivo no sigue el nombre, o si alguna combinación app × tema × idioma quedó sin captura.

## 4. El nombre de los crudos

```
<SHOTS_RAW>/<app>/<pantalla>.<tema>.<idioma>.png
```

`<app>` tiene que ser una app del repo con pantalla (SPA Vite o app móvil), y su tipo decide cómo se revela. `<tema>` tiene que ser `claro` u `oscuro`. Cualquier otro archivo en esas carpetas corta la lectura: revelar a medias dejaría una mezcla de corridas.

## 5. El revelado

Los presets viven en `core/shots_presets.json`, no en el código: las medidas de cada destino cambian por la tienda, no por Consola.

| Destino | Qué hace | Salida |
|---|---|---|
| `landing` | Achica al ancho tope del tipo de app (SPA 1920, móvil 540) con Lanczos, **nunca agranda**, y guarda `.webp` calidad 82 | `<SHOTS_PUBLISH>/<app>/<pantalla>.<tema>.<idioma>.webp` |

La conversión usa Pillow. El revelado no borra nada de `SHOTS_PUBLISH`: un `.webp` de una pantalla que ya no existe queda ahí hasta que alguien lo borre.
