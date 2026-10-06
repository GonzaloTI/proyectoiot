# Documentación del Hardware y Conexión del Proyecto (Basado en arduino.ino)

Esta documentación describe detalladamente cada uno de los componentes de hardware (sensores, actuadores, cables y microcontrolador) que se deducen y utilizan en el código [arduino.ino](file:///c:/Users/Usuario/Documents/python/proyectotecnologia/proyectoiot/arduino.ino). También explica la lógica de funcionamiento y cómo se realiza el ensamblado y conexionado eléctrico de los componentes.

---

## 1. Detalle de Materiales Utilizados

### 🧠 Microcontrolador: ESP32 (DevKit v1 o similar)
El **ESP32** es el cerebro y núcleo del proyecto. Es un SoC (System on a Chip) de bajo costo y bajo consumo de energía con tecnologías Wi-Fi y Bluetooth integradas.
* **Características principales en este proyecto:**
  * **Módulo Wi-Fi:** Se conecta a la red inalámbrica local configurada (`ssid = "gonzalo"`) para enviar los datos de los sensores a un servidor web Flask mediante peticiones HTTP POST en formato JSON.
  * **Pines ADC (Conversor Analógico-Digital):** El ESP32 posee conversores analógicos de 12 bits (resolución de 0 a 4095), lo cual permite leer el voltaje de salida variable de los sensores analógicos de humedad de suelo y de calidad de aire.
  * **Puerto I2C:** Utiliza los pines GPIO 21 (SDA) y GPIO 22 (SCL) para comunicarse digitalmente con el sensor BMP280.
  * **GPIOs Digitales:** Controla el estado del relé a través de una salida digital (GPIO 4).

---

### 🌡️ Sensor BMP280 (Temperatura, Presión Barométrica y Altitud)
Es un sensor de precisión fabricado por Bosch. Mide la temperatura y la presión atmosférica absoluta. A partir de la presión y una referencia estándar (como 1013.25 hPa), estima la altitud.
* **¿Qué hace en el código?**
  * Lee la temperatura ambiente en °C (usada para el algoritmo de control autónomo del relé).
  * Mide la presión barométrica en hPa (hectopascales).
  * Calcula la altitud relativa en metros.
* **Protocolo de comunicación:** **I2C** (Inter-Integrated Circuit). Utiliza dos líneas de datos comunes (SDA y SCL) y requiere una dirección física en el bus, en este caso `0x76`.

---

### 🌫️ Sensor MQ-135 (Calidad del Aire, CO₂ y Humo)
Es un sensor químico analógico diseñado para detectar una amplia variedad de gases contaminantes en el aire, tales como Amoniaco ($NH_3$), Óxidos de Nitrógeno ($NO_x$), Alcohol, Humo y Dióxido de Carbono ($CO_2$).
* **¿Cómo funciona?**
  * Contiene un pequeño calentador interno de óxido de estaño ($SnO_2$) que requiere alimentación constante de **5V** para funcionar adecuadamente. Al exponerse a gases contaminantes, la resistencia interna del sensor varía.
  * En el código, la salida analógica **AO** se conecta al ESP32 (GPIO 34).
  * El código realiza una estimación matemática donde la base mínima es de 400 PPM de CO₂ en aire limpio y escala linealmente según el valor de lectura analógica. También estima la presencia de humo cuando el valor ADC supera el umbral de 700.

---

### 🌱 Sensor de Humedad de Suelo (Higrómetro)
Este sensor mide la cantidad de agua presente en la tierra que rodea a sus sondas metálicas.
* **¿Cómo funciona?**
  * Consta de dos puntas expuestas que se entierran en el suelo. La conductividad eléctrica entre ambas puntas varía dependiendo de cuán húmedo esté el suelo (a mayor agua, menor resistencia y mejor conductividad).
  * La salida analógica **AO** se conecta al GPIO 35.
  * **Calibración:** El código define dos límites para convertir el voltaje analógico a un porcentaje de humedad ($0\%$ a $100\%$):
    * `SOIL_DRY_VAL = 4095` (Lectura analógica cuando el sensor está al aire libre/completamente seco).
    * `SOIL_WET_VAL = 1000` (Lectura analógica cuando el sensor está en tierra muy húmeda o sumergido).

---

### 🔌 Módulo Relé (Relay) de 1 Canal
Es un interruptor de accionamiento electromecánico. Permite controlar cargas de alto voltaje o alta corriente (como una bomba de agua, un foco o un ventilador) usando señales lógicas de bajo voltaje (3.3V o 5V) provenientes del ESP32.
* **Lógica de Activación:**
  * En el código está configurado con **lógica inversa** (`RELAY_ON = LOW` y `RELAY_OFF = HIGH`), muy común en los módulos comerciales para Arduino. Al enviar un nivel bajo (0V) al pin de control `IN` (GPIO 4), el relé se cierra/activa.

---

### 🧷 Cables Jumper (Jumpers)
Son conductores eléctricos flexibles con terminales pre-engarzados en sus extremos. Existen tres tipos básicos:
* **Macho - Hembra (M-F):** Utilizados para conectar directamente los pines del ESP32 (pines macho) a los pines del módulo del sensor o relé (que usualmente son conectores hembra en sus placas de desarrollo).
* **Macho - Macho (M-M):** Si utilizas una placa de pruebas (Protoboard) para interconectar líneas de alimentación comunes.
* **Hembra - Hembra (F-F):** Si conectas pines macho de dos placas diferentes directamente.

---

## 2. Esquema de Conexiones del Proyecto

A continuación se detalla cómo se deben interconectar eléctricamente todos los componentes utilizando los cables jumpers.

### 📋 Tabla de Conexiones

| Componente de Hardware | Pin del Componente | Pin del ESP32 | Descripción / Función |
| :--- | :--- | :--- | :--- |
| **BMP280 (I2C)** | VCC | 3.3V | Alimentación del sensor (3.3V) |
| | GND | GND | Referencia de tierra común |
| | SDA | GPIO 21 | Línea de Datos I2C |
| | SCL | GPIO 22 | Línea de Reloj I2C |
| **MQ-135 (Aire)** | VCC | 5V / VIN | Alimentación del Calentador (5V recomendado) |
| | GND | GND | Referencia de tierra común |
| | AO (Analog Out) | GPIO 34 | Entrada analógica para nivel de gases |
| **Higrómetro (Suelo)**| VCC | 3.3V o 5V | Alimentación del sensor |
| | GND | GND | Referencia de tierra común |
| | AO (Analog Out) | GPIO 35 | Entrada analógica para nivel de humedad |
| **Módulo Relé** | VCC | 5V / VIN | Alimentación de la bobina del Relé (5V) |
| | GND | GND | Referencia de tierra común |
| | IN (Control) | GPIO 4 | Pin de control de salida digital (Lógica Inversa) |

> [!WARNING]
> **Alimentación del MQ-135 y el Relé:** Tanto el MQ-135 (por su resistencia calefactora) como la bobina del relé consumen corriente y rinden mejor a **5V**. Conéctalos al pin **VIN / 5V** del ESP32 (alimentado por USB). Los sensores lógicos como el **BMP280** operan estrictamente a **3.3V** para evitar dañar sus pines de comunicación I2C.

---

### 🗺️ Diagrama de Flujo y Conexiones del Hardware

```mermaid
graph TD
    ESP32[Microcontrolador ESP32]
    
    subgraph I2C [Bus de Comunicación I2C]
        BMP280["Sensor BMP280 (Temp / Presión)"]
    end
    
    subgraph AnalogInputs [Entradas Analógicas]
        MQ135["Sensor MQ-135 (Calidad de Aire)"]
        SoilSensor["Sensor Humedad Suelo (Higrómetro)"]
    end

    subgraph Actuators [Actuadores Digitales]
        Relay["Módulo Relé (GPIO 4)"]
    end
    
    %% Conexiones I2C
    ESP32 -- "GPIO 21 (SDA)" --> BMP280
    ESP32 -- "GPIO 22 (SCL)" --> BMP280
    ESP32 -- "3.3V (VCC)" --> BMP280
    ESP32 -- "GND" --> BMP280
    
    %% Conexiones Analógicas
    ESP32 -- "GPIO 34 (AO)" <-- MQ135
    ESP32 -- "5V (VIN)" --> MQ135
    ESP32 -- "GND" --> MQ135
    
    ESP32 -- "GPIO 35 (AO)" <-- SoilSensor
    ESP32 -- "3.3V (VCC)" --> SoilSensor
    ESP32 -- "GND" --> SoilSensor
    
    %% Conexiones Actuador
    ESP32 -- "GPIO 4 (IN) - Output" --> Relay
    ESP32 -- "5V (VIN)" --> Relay
    ESP32 -- "GND" --> Relay
```

---

## 3. Resumen del Funcionamiento Lógico (del Código `arduino.ino`)

1. **Configuración Inicial (`setup`)**:
   * Se configuran los modos de pines (`OUTPUT` para el relé, `INPUT` para MQ-135 y Humedad de Suelo).
   * Se inicia la comunicación I2C en los pines 21 y 22.
   * Se inicializa el sensor BMP280 con dirección `0x76` (si falla, detiene el programa por seguridad).
   * Se conecta a la red WiFi. Si no se logra tras 20 intentos (10 segundos), el programa continúa operando en **Modo Local Autónomo**.

2. **Bucle de Medición (`loop`)**:
   * **Lecturas Digitales/I2C:** Se consultan los valores del BMP280 (temperatura, presión y estimación de altitud).
   * **Lecturas Analógicas:**
     * Se lee el sensor MQ-135 en el GPIO 34 y se convierte a PPM de $CO_2$ e indica humo si la lectura analógica es mayor a 700.
     * Se lee el higrómetro en el GPIO 35 y se mapea linealmente entre el rango seco (4095) y húmedo (1000) para calcular un porcentaje de humedad entre $0\%$ y $100\%$.
   * **Envío HTTP:** Si está conectado al WiFi, envía todas las variables recopiladas y el estado del relé en un payload JSON hacia el servidor Flask (`http://10.86.129.92:5000/api/datos`).

3. **Toma de Decisiones / Control de Relé**:
   * **Si hay comunicación exitosa con el servidor:**
     * El servidor puede ordenar el **Modo Manual** enviando un comando `relay_command` (`ON` u `OFF`), el cual el ESP32 acata.
     * Si el servidor indica **Modo Automático**, el ESP32 ejecuta su lógica local: `controlAutonomoLocal(temperatura)`.
   * **Si NO hay WiFi o el servidor falla:**
     * El ESP32 activa el **Modo Automático de Respaldo Local**, donde enciende el relé si la temperatura leída es igual o mayor a **$27.0^\circ\text{C}$**, y lo apaga si es menor.
