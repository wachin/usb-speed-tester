# ¿Tu pendrive USB 3.0 realmente funciona a velocidad SuperSpeed en Linux? Cómo comprobarlo desde la terminal

Llevo en el mundo de GNU/Linux desde el año 2007 y, a pesar del tiempo y la experiencia, la tecnología siempre encuentra formas de darnos sorpresas sobre detalles que solemos dar por sentados.

Hace poco conecté un pendrive USB 3.0 a un puerto USB 3.0 SS (SuperSpeed) de mi equipo y me surgió una duda razonable: **¿Realmente el sistema está negociando la velocidad a USB 3.0 o se quedó limitado a USB 2.0? Y más importante, ¿la velocidad real de lectura y escritura refleja lo que promete la etiqueta?**

Si alguna vez te has hecho la misma pregunta, en este tutorial te enseño cómo diagnosticar la velocidad de tus dispositivos USB desde la terminal de forma sencilla.

---

## 1. Comprobar la velocidad de enlace con `lsusb -t`

El primer paso no es medir la velocidad de transferencia, sino verificar **a qué velocidad han negociado el puerto y el pendrive a nivel de hardware**.

Abre tu terminal y ejecuta:

```bash
lsusb -t

```

Este comando muestra el árbol de dispositivos USB y sus controladores activos. Si conectas primero un dispositivo USB 2.0 y luego uno USB 3.0 en el mismo puerto físico, notarás algo muy interesante en la salida:

```text
/:  Bus 001.Port 001: Dev 001, Class=root_hub, Driver=xhci_hcd/12p, 480M
    |__ Port 001: Dev 006, If 0, Class=Mass Storage, Driver=usb-storage, 480M
...
/:  Bus 002.Port 001: Dev 001, Class=root_hub, Driver=xhci_hcd/6p, 5000M
    |__ Port 001: Dev 002, If 0, Class=Mass Storage, Driver=usb-storage, 5000M

```

### ¿Cómo interpretar este resultado?

* **Controlador xHCI:** Los controladores USB 3.0 (`xhci_hcd`) crean dos *Root Hubs* virtuales para gestionar el bus:
* **Bus 001 (480M):** Administra las líneas USB 2.0 (High Speed, máximo teórico de 480 Mbps).
* **Bus 002 (5000M):** Administra las líneas USB 3.0 (SuperSpeed, máximo teórico de 5000 Mbps o 5 Gbps).


* **El valor `5000M`:** Si tu pendrive aparece agrupado en el bus de **5000M**, significa que el hardware, el cableado interno y el sistema operativo han negociado exitosamente el enlace a **USB 3.0 SuperSpeed**.

---


### 2. Medir la velocidad de LECTURA real con `hdparm`

Que el enlace esté negociado a 5 Gbps no significa que la memoria física de tu pendrive alcance esa cifra. Ciertas memorias USB económicas usan componentes más lentos.

Antes de ejecutar la prueba, debemos listar los dispositivos de almacenamiento conectados con el comando `lsblk`:

```bash
lsblk

```

En la terminal obtendrás una salida similar a esta:

```text
NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda      8:0    0 447,1G  0 disk 
├─sda1   8:1    0   100M  0 part /boot/efi
└─sda5   8:5    0 231,5G  0 part /
sdb      8:16   1  57,3G  0 disk 
└─sdb1   8:17   1  57,3G  0 part /media/USB-DATA

```

#### ⚠️ ¡Atención a la diferencia entre `/dev/sdb` y `/dev/sdb1`!

* **`/dev/sdb` (El disco completo):** Es el dispositivo físico en su totalidad.
* **`/dev/sdb1` (La partición):** Es la división lógica dentro del pendrive donde residen tus archivos y que se monta en `/media/USB-DATA`.

El comando `hdparm` evalúa el rendimiento del hardware a bajo nivel, por lo que **debemos apuntar al disco completo (`/dev/sdb`) y NO a la partición (`/dev/sdb1`)**:

```bash
sudo hdparm -tT /dev/sdb

```

Obtendrás una salida como esta:

```text
/dev/sdb:
 Timing cached reads:   10850 MB in  1.99 seconds = 5452.02 MB/sec
 Timing buffered disk reads: 194 MB in  3.02 seconds =  64.18 MB/sec

```

* **`Timing cached reads`:** Mide la lectura desde la caché en RAM del sistema (evalúa el rendimiento de tu procesador y memoria).
* **`Timing buffered disk reads`:** Es la **velocidad real de lectura física** del pendrive.

> **Dato clave:** En USB 2.0, el límite práctico real rara vez supera los **30 a 40 MB/s**. Si obtienes valores por encima de **60 MB/s**, tienes la prueba definitiva de que estás leyendo a velocidades de USB 3.0.

---

*(Nota: En la sección 3 con `dd`, la prueba se hace navegando a `/media/USB-DATA`, que corresponde a la partición montada `sdb1`).*
---

## 3. Medir la velocidad de ESCRITURA real con `dd`

Medir la escritura es crucial porque escribir en un chip de memoria flash requiere operaciones complejas de borrado de bloques que suelen ser bastante más lentas.

Para medir la velocidad de escritura copiando un archivo temporal de 1 GB, navega a la carpeta donde está montado tu USB (por ejemplo `/media/USB-DATA`) y ejecuta:

```bash
dd if=/dev/zero of=test_escritura.tmp bs=1M count=1000 status=progress conv=fdatasync && rm test_escritura.tmp

```

Resultado de ejemplo:

```text
1048576000 bytes (1,0 GB, 1000 MiB) copied, 55,3205 s, 19,0 MB/s

```

### ¿Por qué obtengo ~19 MB/s de escritura si estoy en USB 3.0?

Es completamente normal. En memorias USB de gama de entrada o consumo general:

* La **lectura** suele oscilar entre 60 y 100 MB/s.
* La **escritura** suele quedarse entre 15 y 25 MB/s debido a la falta de caché de alta velocidad (DRAM) en el controlador del pendrive.

---

## Conclusión

1. **`lsusb -t`** te dice si el pendrive **conecta** como USB 3.0 (`5000M`).
2. **`hdparm`** te dice cuán rápido **lee** el dispositivo.
3. **`dd`** te muestra la velocidad real a la que **escribe**.

Con estos tres comandos puedes diagnosticar fácilmente si un puerto o pendrive está fallando, o simplemente si el fabricante ahorró costos en la velocidad del chip de memoria. ¡La terminal de Linux nunca miente!
