# Favoritos — separar las cuatro acciones de todos los días de las cuarenta que existen

El rail declara 43 acciones. Un repo cualquiera usa cinco o seis: el resto son operaciones de
arranque (`bootstrap_vps`), de limpieza (`purge_images`) o de otro perfil de proyecto. Filtrar por
texto ya existía, pero exige saber de antemano qué buscás; esto es para lo contrario: tener a un
clic lo que usás sin pensar.

## 1. La marca es del repo, no de la app

Un repo Flutter no comparte favoritos con uno que despliega a un VPS. Se guardan en `QSettings`
bajo `favorites/<ruta-del-repo>` (`ui/favorites.py`), igual que el orden de pestañas — sobrevive al
cierre y no ensucia el repositorio con un dato que es de esta máquina.

El interruptor, en cambio, es de la app: `favorites/only`. Es un modo de la vista, no del proyecto.

## 2. Dónde se marca: la cabecera de la acción, no el panel de parámetros

La estrella vive en la cabecera de la columna derecha (`ui/tab_panel.py`), al lado del nombre de la
acción abierta. Puesta entre las casillas del panel de parámetros se leería como un parámetro más,
y no lo es: los parámetros son de **esta corrida**, el favorito es del **repo**. La separación
física dice la diferencia sin necesidad de explicarla.

## 3. Un interruptor global, con escape por caja

En vez de un interruptor por grupo (ocho estados independientes que recordar), hay uno solo junto
al filtro: *solo favoritos*. Cada caja muestra entonces `1/4` en lugar de `4`, y **ese contador es
el escape**: un clic abre esa caja entera sin apagar el interruptor, otro clic la vuelve a podar.
Las cajas sin ninguna favorita desaparecen, reusando el mismo mecanismo del filtro de texto.

Con el interruptor puesto las cajas quedan abiertas y el acordeón se suspende: ya están podadas,
caben todas, y la gracia del modo es llegar a la acción en un clic y no en dos.

## 4. Escribir en el filtro busca sobre todo

Aunque el interruptor esté puesto, escribir en el filtro busca entre las 43 acciones. Buscar es ir
por algo puntual —muchas veces justamente lo que no usás nunca— y esconderlo por no estar marcado
sería un chiste cruel. El interruptor gobierna el estado en reposo del rail; el texto lo levanta.

## 5. La señal, viendo todo

La acción favorita conserva el filete de acento a la izquierda de forma permanente y el texto en el
color vivo, aun con el interruptor apagado. Es el mismo recurso que usan las destructivas (que lo
llevan en rojo): así, viendo la lista completa, se distingue de un vistazo lo tuyo de lo demás.

## 6. Estado de implementación

| Archivo | Estado |
|---|---|
| `ui/favorites.py` | ✅ marcas por repo y modo de la vista, en `QSettings` |
| `ui/widgets/switch.py` | ✅ `ToggleSwitch` (pastilla) y `StarToggle` (estrella de cabecera) |
| `ui/widgets/group_card.py` | ✅ filete permanente, contador `n/total` y espiar por caja |
| `ui/rail.py` | ✅ interruptor global, recarga al cambiar de repo, acordeón suspendido |
| `ui/tab_panel.py` | ✅ estrella en la cabecera, señal `favorites_changed` |
