# 19 · Imágenes

El grupo **Imágenes** produce el material gráfico de las apps de un repo. Hoy tiene las capturas publicables; `generate_icons` está declarado sin cuerpo ([30](30_riesgos_y_pendientes.md)).

## 1. El corte: el repo pone la cámara, Consola el revelado

| Parte | Quién | Dónde |
|---|---|---|
| Sembrar datos ficticios, entrar sin login, navegar, sacar el PNG | el script del repo | lo que declara `SHOTS_CMD` |
| Elegir apps, temas, idiomas y emulador; encender el emulador | Consola | `core/tasks/images.py::shoot_screens` |
| Validar lo que dejó la cámara | Consola | `core/shots.py::collect`, `missing_combinations` |
| Convertir cada crudo para cada destino y escribir el manifiesto | Consola | `core/shots.py` (`render_*`, `write_manifest`), `core/shots_presets.json` |

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

Eje de `render_shots` y de la compuesta: `destinations` (`landing`, `play`, `appstore`, `manual`, `og`, `social`, `presskit`). Un destino sin preset, o sin ningún crudo de un tipo que le sirva, corta la corrida antes de convertir nada.

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
| `play` | Solo crudos móviles. No cambia la medida: el crudo tiene que tener el lado corto ≥ 320 px, el largo ≤ 3840 px y una proporción ≤ 2:1 | `<SHOTS_DIST>/play/<idioma>/<app>/<pantalla>.<tema>.png` |
| `appstore` | Solo crudos móviles. Medida exacta: 1290×2796 (iPhone 6.9") o 2064×2752 (iPad 13"), la que se alcance recortando como mucho un 3 % | `<SHOTS_DIST>/appstore/<idioma>/<app>/<pantalla>.<tema>.{iphone,ipad}.png` |
| `og` | Solo crudos SPA. 1200×630, recortando lo que haga falta | `<SHOTS_DIST>/og/<idioma>/<app>/<pantalla>.<tema>.og.png` |
| `social` | Cuadrado 1080×1080 de todo crudo; historia 1080×1920 solo de móviles. Recorta lo que haga falta | `<SHOTS_DIST>/social/<idioma>/<app>/<pantalla>.<tema>.{square,story}.png` |
| `manual` | PNG a resolución nativa | `<SHOTS_DIST>/manual/<idioma>/<app>/<pantalla>.<tema>.png` |
| `presskit` | Los crudos tal cual, sin comprimir, en un ZIP | `<SHOTS_DIST>/presskit/capturas.zip` (`<app>/<pantalla>.<tema>.<idioma>.png` dentro) |

`core/shots.py::plan` decide qué sale de cada crudo, con los datos del preset:

- `kinds`: de qué tipos de app sale el destino. Si ningún crudo es de esos tipos, corta.
- `limits`: reglas que el crudo tiene que cumplir tal cual. Si uno no las cumple, corta y lo nombra.
- `sizes` con `max_crop`: medidas exactas. Cada crudo va a las medidas cuya proporción alcanza recortando como mucho `max_crop` de la imagen. Así un teléfono va a iPhone y una tablet a iPad sin que el contrato con la cámara diga qué dispositivo es. Si un crudo no cabe en ninguna, corta y lo nombra: recortar de más se come la barra superior o la navegación de la app.

Las medidas fijas se obtienen escalando hasta cubrir (aquí **sí** se agranda: la medida es exacta) y recortando del centro. Todo PNG de estos destinos sale sin canal alfa, que las dos tiendas rechazan.

Un teléfono 1080×2400 sirve para App Store (recorta 2,5 %) y no para Play (2,22:1). Uno 1080×2160 sirve para Play y no para App Store (recortaría 7,7 %). **Ninguna proporción de teléfono sirve para las dos**: son dos tandas, sacadas con dispositivos distintos.

Cada destino deja un `capturas.json` en su carpeta: `{destination, items}` con app, pantalla, tema, idioma, archivo, medida y `sha256` de cada archivo (en el press kit, el del crudo, con su `member` dentro del ZIP). Sin fecha y ordenado: dos corridas iguales dan el mismo archivo. Antes de reescribirlo se compara con el anterior, y el log dice qué archivos **cambiaron**, cuáles son **nuevos** y cuáles **ya no están**. Esa es la regresión visual.

Se planean todos los destinos marcados antes de convertir ninguno. El revelado no borra nada de lo que ya hay en `SHOTS_PUBLISH` ni en `SHOTS_DIST`: un archivo de una pantalla que ya no existe queda ahí hasta que alguien lo borre, y el manifiesto es la lista de lo vigente.

La conversión usa Pillow.
