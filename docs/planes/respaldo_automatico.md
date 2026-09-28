# Plan — respaldo automático fuera de la máquina

> **Estado (verificado 2026-09-28).** No hay nada construido. Hoy el único respaldo es el botón
> `backup_db`, que vuelca a esta máquina cuando alguien lo presiona
> ([16](../arquitectura/16_base_de_datos.md), §8).
>
> **Decidido el 2026-09-28:** cada VPS se respalda solo, fuera de su máquina, y todo lo del
> respaldo es configurable por repo. Si un respaldo no llega, avisa el monitor de Equipaggio, y el
> mismo monitor avisa cuando un VPS se queda sin disco. Lo demás es propuesta.

## 1. Síntoma

| Hoy | Qué pasa |
|---|---|
| `backup_db` es manual | Si nadie lo presiona, no hay respaldo. Una migración mala o un `DELETE` equivocado no tienen vuelta |
| `banditore` ADR-0037 propone un volcado nocturno en el mismo VPS | Si se pierde el VPS, se pierden la base y su respaldo juntos |

## 2. Qué hace

Consola instala en el VPS del repo un temporizador de systemd que vuelca la base con `pg_dump`,
sube el volcado al destino configurado y borra los viejos de ese destino.

Corre **en el VPS**, no en esta máquina: esta computadora puede estar apagada a la hora del
respaldo. Es lo contrario de lo que [ADR-0046](../adr/0046-el-volcado-corre-de-este-lado.md) decidió
para el botón manual, así que va con un ADR propio cuando se construya.

## 3. Configuración *(propuesta: nombres de las claves)*

Claves de `config.env`, como `BACKUP_DIR` y `BACKUP_KEEP` ([ADR-0045](../adr/0045-la-carpeta-y-el-conteo-de-respaldos-son-configuracion.md)).
Ninguna tiene valor por omisión: sin ellas, el botón que instala el respaldo no corre.

| Clave | Qué dice | Ejemplo |
|---|---|---|
| `AUTO_BACKUP_SCHEDULE` | Cuándo corre, en formato `OnCalendar` de systemd | `*-*-* 03:30` |
| `AUTO_BACKUP_DEST` | A dónde sube el volcado | `b2:respaldos/banditore` |
| `AUTO_BACKUP_KEEP` | Cuántos volcados se conservan en el destino. Falla ruidosamente si no es un entero de 1 o más, igual que `BACKUP_KEEP` | `14` |
| `AUTO_BACKUP_DEST_CREDENTIALS` | Credenciales del destino. `secret` | — |
| `AUTO_BACKUP_KEY` | Llave con la que se cifra el volcado antes de salir del VPS. `secret` | — |

### Destinos posibles *(propuesta: rclone, que habla con todos)*

| Destino | A favor | En contra |
|---|---|---|
| Almacenamiento en la nube (Backblaze B2, S3 o compatible) | Barato, y no depende de ninguna máquina propia | Un proveedor más, con su cuenta |
| Otro VPS propio por SFTP (el de Equipaggio) | Sin proveedor nuevo | También es una sola máquina |

## 4. Piezas

| Pieza | Qué hace |
|---|---|
| Botón «Configurar respaldo automático» | Escribe el servicio y el temporizador en el VPS, con las claves de la sección 3 |
| Servicio de respaldo | `pg_dump -Fc`, cifrado, subida al destino y rotación por `<DB_NAME>-*.dump`, igual que `backup_db` |
| Restaurar desde el destino | Baja un volcado del destino a `BACKUP_DIR` y lo carga con el `restore_db` de hoy *(propuesta)* |
| Borrado | `remove_systemd_service` también borra el servicio y el temporizador del respaldo |
| Aviso al monitor | Al terminar bien, el servicio de respaldo le avisa al monitor de Equipaggio. Si el aviso no llega a tiempo, el monitor avisa por push (plan `construccion_inicial.md` de `equipaggio`, sección 3) |
| Reporte de disco | Un temporizador aparte le reporta al monitor el espacio libre del VPS *(propuesta: cada hora)*. Va aparte del respaldo porque un VPS sin base también tiene disco, y un día es mucho para un disco que se llena con logs |

### Claves del aviso *(propuesta)*

| Clave | Qué dice |
|---|---|
| `MONITOR_URL` | A dónde se reportan el respaldo y el disco |
| `MONITOR_TOKEN` | Con qué se identifica el VPS ante el monitor. `secret` |

## 5. Preguntas abiertas

1. **¿Qué destino usa cada repo?** Es configurable, así que no hay que decidirlo de una vez para
   todos; sí para el primero que lo use.
2. **¿Con qué se cifra?** `rclone crypt` o `age`. Los volcados llevan datos personales.
3. **¿Cómo sabe el monitor cuánto esperar?** El horario es configurable por repo, así que la espera
   de cada VPS no puede ser fija. Candidatos: que el aviso diga cuándo toca el siguiente, o que el
   registro del monitor guarde la espera de cada VPS.
