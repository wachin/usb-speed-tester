# Cómo reconocer un puerto SuperSpeed (USB 3.x)

Cuando el **Registro Técnico** informa `5000M`, el puerto y el dispositivo
acordaron comunicarse en **USB 3.x SuperSpeed — 5 Gbps**. Esa es la buena
noticia. Este tutorial te enseña a *ver* ese puerto con tus propios ojos, para
que siempre conectes un dispositivo rápido en el conector correcto.

El truco es una pequeña marca impresa o grabada **a pocos milímetros del
conector**: las letras **SS**, de *SuperSpeed*.

---

## 1. El símbolo SS junto al tridente USB

Este es el símbolo exacto que debes buscar. Combina las dos letras **SS** con el
logotipo del tridente USB:

![Las letras SS junto al logotipo del tridente USB, rotulado USB 3.0](usb3-ss-logo.png)

Lo encontrarás en el plástico del puerto, en el chasis junto a él, o en la
etiqueta debajo de la laptop. En muchos equipos la lengüeta de plástico *dentro*
del puerto también es **azul** en lugar de negra.

---

## 2. Una sola marca puede cubrir varios puertos

Los fabricantes suelen imprimir el símbolo una sola vez y usar una llave o una
flecha para indicar a qué puertos corresponde. Todos los puertos que la llave
señala son SuperSpeed:

![Dos puertos USB azules compartiendo una marca SS, comparados con un puerto USB 2.0](usb3-ss-ports.png)

| Marca junto al puerto        | Lengüeta dentro del puerto | Velocidad de enlace |
|------------------------------|----------------------------|---------------------|
| **SS** + tridente USB        | azul                       | 5 Gbps (5000M)      |
| sin marca                    | negra                      | 480 Mbps (USB 2.0)  |

---

## 3. Mira el costado de tu propia laptop

En una laptop la marca está grabada en el chasis, justo al lado del conector. Es
pequeña, así que acércate y mírala con atención:

![La marca SS grabada en el chasis de una laptop junto a un puerto USB azul](usb3-ss-laptop.png)

Si el puerto que usaste no tiene la marca **SS**, el dispositivo solo puede
negociar USB 2.0, sin importar lo bueno que sea el pendrive.

---

## ¿Por qué un puerto rápido sigue leyendo lento?

Un enlace SuperSpeed solo fija el *techo*. La velocidad real depende de tres
cosas distintas, y el programa mide cada una por separado:

- **El análisis del bus** (`lsusb -t`) te dice qué techo se negoció: `5000M`
  para USB 3.x, `480M` para USB 2.0.
- **El benchmark de lectura** (`hdparm`) y los números de **fio** te dicen qué
  tan rápido es realmente el chip de memoria flash. Un pendrive económico en un
  puerto USB 3 perfecto suele leer a 60–150 MB/s y escribir a 15–25 MB/s. Eso es
  la memoria, no el puerto.
- **El benchmark de escritura** (`dd`) importa porque escribir en flash requiere
  ciclos de borrado y programación, y por eso la escritura siempre es mucho más
  lenta que la lectura en dispositivos de consumo.

Así que un pendrive que lee a 58 MB/s en un puerto `5000M` no está averiado: el
puerto está bien y el chip de memoria es el límite.

---

## Lista de verificación rápida

1. Busca la marca **SS** junto al puerto que quieres usar.
2. Prefiere el puerto con la lengüeta **azul**.
3. Conecta el dispositivo y ejecuta **Bus Analysis**: debe informar `5000M`.
4. Compara los números de lectura y escritura con los rangos de arriba.
5. Si el análisis informa `480M`, mueve el dispositivo a otro puerto del mismo
   equipo; el cable, un hub o el propio dispositivo también pueden ser la causa.
