¿Cómo funciona la llave guardada fuera?	install.py recibe dos llaves: la de esta computadora (VPS_KEY_NAME) y OFFLINE_KEY. Las dos entran por SSH a la cuenta (--key) y las dos firman releases (--signer). Si pierdes la computadora, con la otra sigues entrando y desplegando. Ojo: hoy la tuya es de prueba y está en esta misma máquina.

¿Permisos del navegador deberían ir en el código?	Sí: qué funciones del navegador usa la app es un dato de su código. Hoy vive en config.env, que no se versiona. Para derivarlo como coturn, canone tiene que definir dónde lo declara el repo.

¿Consola puede pedirle la IP del túnel a Equipaggio?	Hoy no: en canone no hay ninguna API para eso. Además no basta con la IP: Equipaggio también tiene que registrar la llave WireGuard que install.py genera en el VPS. Haría falta un endpoint en Equipaggio que reciba esa llave y devuelva la IP.
