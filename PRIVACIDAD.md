# Privacidad

ThreadEyes lee los registros de tus conversaciones de Claude Code, que pueden contener código, nombres de clientes y datos privados. Esta página dice exactamente qué hace con ellos. English: [PRIVACY.md](PRIVACY.md).

**En una línea: funciona en tu ordenador, no hace ninguna petición de red y no guarda nada salvo dos archivos de informe que puedes abrir y borrar.**

## Qué lee

- Todos los archivos `*.jsonl` de la carpeta de registros de Claude Code: `~/.claude/projects`, o la carpeta que le pases con `--logs`, o `CLAUDE_CONFIG_DIR/projects`.
- De cada línea mira solo: el título del hilo (`customTitle`), la carpeta de trabajo (`cwd`), la marca de tiempo, el nombre del modelo, el recuento de tokens (`usage`) y el **nombre** de cada herramienta que usó el asistente.
- En las herramientas de terminal (Bash, PowerShell) mira la **primera palabra** de cada orden, solo para distinguir «ejecutar o probar» de «leer». La orden en sí no se guarda.
- Para leer una línea el programa la carga entera en memoria, así que el texto de la conversación pasa por la memoria. No lo mira, no lo guarda ni lo escribe en ningún sitio.
- Opcionalmente, un archivo de configuración que escribas tú: `--config ARCHIVO`, o `threadeyes.json` en la carpeta desde la que lo ejecutes, o `~/.threadeyes.json`.

## Qué guarda

Solo dos archivos, en la carpeta de salida (`threadeyes-output` por defecto):

- `threadeyes-report.md`
- `threadeyes-panel.html`

Contienen: nombres de hilos, el nombre de la última carpeta de cada directorio de trabajo, fechas, el gasto solo en porcentajes (del total o de una semana normal, nunca un importe), nombres de modelos y el reparto de tipos de acción (construir, probar, leer, coordinar). **No** contienen texto de conversaciones, órdenes, contenido de archivos ni rutas aparte del nombre de la última carpeta.

**Cuidado al compartirlos o al hacer capturas:** los nombres de hilos y de carpetas pueden delatar. Revísalos antes. Los datos de `examples/` son inventados.

## Lo que no hace

- **Sin red.** Usa solo la biblioteca estándar de Python y nunca abre una conexión. El panel no carga nada de internet: su librería de gráficos va incluida en el archivo, así que funciona sin conexión.
- **Sin telemetría, sin cuenta, sin seguimiento, sin analítica.**
- **Sin base de datos, caché ni historial.** Cada ejecución vuelve a leer los registros y reescribe los dos archivos. El programa ni siquiera deja la carpeta `__pycache__` de Python, y el panel no guarda nada en tu navegador.
- **No modifica tus registros, tu configuración de Claude Code ni ningún otro archivo.**

## Cómo puedes comprobarlo

- Es de código abierto (licencia MIT): lee `threadeyes.py`, `panel.py` e `i18n.py`. Busca `socket`, `urllib`, `http` y `requests`: no hay código de red.
- Ejecútalo sin conexión. Funciona igual.
- Abre `threadeyes-panel.html` y mira la pestaña de red del navegador: ninguna petición.

## Si compartes tus informes

Un informe es tan privado como los nombres de hilo que lleva. Si lo publicas, quita o cambia lo que no quieras enseñar.

## Quitarlo

Borra la carpeta de ThreadEyes y la de salida. No se instaló ni se guardó nada más.
