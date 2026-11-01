# ADR-0067 · «Publicar versión» sube el último tag de origin, y «Desplegar versión» elige entre los releases firmados

- **Estado:** Aceptada
- **Fecha:** 2026-10-31
- **Alcance:** core/tasks/vps_release.py, core/tasks/vps_setup.py, core/canone.py, core/catalog.py

## Contexto

canone despliega un tag `vX.Y.Z`: el `release.yml` del repo publica el artefacto y su `.sha256`, el `.sha256` se firma fuera de GitHub con `ssh-keygen -Y sign -n deploy`, y `deploy.py` lo instala por `ssh` (despliegue.md de canone, «Versiones»). canone no fija de dónde sale el número ni cómo elige quien despliega la versión que instala.

## Decisión

1. **El número sale del tag `v*` más alto de origin**, subido por el eje `part` (major, minor o patch) de «Publicar versión». Sin tags, sube desde `v0.0.0`. No toca ningún manifiesto ni crea commits. Cuentan los tags de origin (`git ls-remote`), no los locales (`canone.next_tag`).
2. **«Publicar versión» encadena crear el tag → esperar `release.yml` → firmar → desplegar**, con una casilla por paso. Se firma con `VPS_KEY_NAME`, la misma llave del primer `--signer` (ADR-0066).
3. **«Desplegar versión» elige entre los releases publicados que traen su `<app>-<tag>.sha256.sig`**, consultados en GitHub con `gh api`.
4. **El último paso de «Configurar VPS» despliega el último release publicado**, el que GitHub da como `latest`, si tiene su firma. Sin releases o sin firma, falla y dice qué falta. Si `/srv/<app>/current` ya es ese release, no hace nada.
5. *(propuesta)* **Crear el tag corta si hay cambios sin commitear o commits que origin no tiene.** El CI construye el commit del tag en GitHub, no la carpeta de esta máquina.
6. *(propuesta)* **Sin «Crear tag», «Publicar versión» firma y despliega el último release publicado**: retoma una publicación que cortó después del CI.
7. *(propuesta)* **Un release que ya tiene su firma no se vuelve a firmar.**
8. *(propuesta)* **La corrida de `release.yml` se sigue con `gh run view` cada 15 segundos**, y no con `gh run watch`, que redibuja la terminal. Si no termina bien, se muestra `gh run view --log-failed` y corta.

## Consecuencias

- Hace falta GitHub CLI (`gh`) en esta máquina, con `gh auth login` hecho.
- `deploy.py` falla si la versión ya está en `/srv/<app>/releases/`, donde quedan las cinco más nuevas: «Desplegar versión» no sirve hoy para volver a la activa ni a una de esas cinco *(hallazgo de lectura, sin confirmar)*. Volver a una de ellas pide un programa en canone.
- Un tag que se crea y no se empuja queda local; el siguiente intento no lo cuenta y falla al crear un tag con el mismo nombre.

## Descartado

- **Leer el número de `server/pyproject.toml`.** Pide un commit con el número subido antes de cada publicación, y el tag ya es la versión que despliega canone.
- **Escribir el tag a mano.** Deja a quien publica calcular el siguiente número.
- **Escribir el tag a mano en «Desplegar versión».** Ofrecería tags sin firma, que `deploy.py` rechaza.
