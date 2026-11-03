# ADR-0074 · Lo que deja un cambio permanente en un VPS y ningún programa de canone hace va primero a canone

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** todo lo que Consola hace en un VPS

## Contexto

El ADR-0107 de canone dejó de pedirle esto a Consola: canone no nombra la herramienta que corre sus programas. Consola adoptó la regla como propia el 2026-10-30 (pregunta 14 del plan de despliegue).

## Decisión

1. **Lo que deja un cambio permanente en un VPS y ningún programa de canone hace se agrega primero a canone.**
2. **No alcanza** a lo que corre en esta máquina (compilar, crear el tag, firmar), a correr lo que canone ya instaló (`deploy.py`, `credentials.py`, `systemctl`, los registros, la salud), ni a lo que canone deja a quien prepara la máquina o despliega, como sus paquetes, el swap o la llave de una receptora.

## Consecuencias

- «Vaciar VPS», «Restaurar» en el VPS y el ámbito remoto de la base esperan su programa en canone.
- «Quitar acceso SSH» edita `authorized_keys` de la cuenta que administra, y canone no trae un programa para eso. Es un incumplimiento abierto, anotado en el 30.
- «Compilar ejecutable» sube al VPS fuera de `deploy.py`. También está en el 30.

## Descartado

- **Que Consola lo resuelva por su cuenta en el VPS.** Es la segunda copia de lo que canone fija que este repo salió de sostener con el [ADR-0059](0059-desplegar-con-los-programas-de-canone.md).
