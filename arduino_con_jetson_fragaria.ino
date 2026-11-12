/*
 * =========================================================================================
 * Proyecto: Monitoreo IoT + Visión Artificial de Fragaria / Fresa (Jetson Nano + ESP32)
 * Archivo:  arduino_con_jetson_fragaria.ino
 * =========================================================================================
 * Conexión física directa con NVIDIA Jetson Nano (Conector 40 Pines):
 *   - ESP32 GPIO 16 (RX2) <--- Conectar a Pin 8  'D14 (TXD)' de la Jetson Nano
 *   - ESP32 GPIO 17 (TX2) ---> Conectar a Pin 10 'D15 (RXD)' de la Jetson Nano
 *   - ESP32 GND           <---> Conectar a Pin 6, 9 o 14 'GND' de la Jetson Nano
 *
 * Conexión de Relés:
 *   - Relé 1: GPIO 4
 *   - Relé 2: GPIO 5
 *
 * Sensores conectados al ESP32:
 *   - BMP280 (I2C): SDA en GPIO 21, SCL en GPIO 22
 *   - MQ-135 (Gas/Humo/CO2): Pin AO en GPIO 34 (ADC1)
 *   - Sensor Humedad Suelo:  Pin AO en GPIO 35 (ADC1)
 * =========================================================================================
 */

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// --- Pines I2C y Sensores Analógicos ---
#define SDA_PIN 21
#define SCL_PIN 22
#define SOIL_MOISTURE_PIN 35 // Sensor humedad de suelo en GPIO 35
#define MQ135_PIN 34         // Sensor MQ-135 en GPIO 34

// --- Pines de los Relés y LED ---
#define RELAY_1_PIN 4 // Pin GPIO para Relé 1
#define RELAY_2_PIN 5 // Pin GPIO para Relé 2
#define LED_PIN 2     // LED integrado en ESP32

// Lógica de activación de relé:
#define RELAY_ON LOW
#define RELAY_OFF HIGH

// --- Pines UART Serial2 para Jetson Nano ---
#define RXD2 16
#define TXD2 17

// --- Calibración para Sensor de Humedad de Suelo (ADC 12-bits: 0 - 4095) ---
const int SOIL_DRY_VAL = 4095;
const int SOIL_WET_VAL = 1000;

// --- Configuración de Red WiFi ---
const char* ssid = "gonzalo";
const char* password = "1234567899";

// --- Dirección IP / Dominio del Servidor Flask en Render ---
const char* serverName = "https://proyectoiot-l4mo.onrender.com/api/datos";

// Instancia BMP280
Adafruit_BMP280 bmp;

// Estados de los relés
bool relay_1_activo = false;
bool relay_2_activo = false;

// Variables de control de Modo
bool modoManualWeb = false;         // True si desde la Web se activó 'Modo Manual'
bool controlJetsonActivo = false;   // True si la Jetson Nano está transmitiendo por UART
unsigned long ultimoComandoJetson = 0;
const unsigned long TIMEOUT_JETSON_MS = 6000; // Margen de 6 segundos sin mensajes de Jetson

// Variables para almacenar la detección del Modelo Fragaria
int fragaria_total = 0;
String fragaria_clase = "Ninguna";
float fragaria_conf = 0.0;
bool fragaria_enfermedad = false;

// Temporizador no bloqueante para envío HTTP a Flask (cada 4 segundos)
unsigned long ultimoEnvioHttp = 0;
const unsigned long INTERVALO_HTTP_MS = 4000;

void setup() {
  // 1. Inicializar Serial USB (para depuración en PC)
  Serial.begin(115200);

  // 2. Inicializar Serial2 para comunicación UART con Jetson Nano (115200 baudios)
  Serial2.begin(115200, SERIAL_8N1, RXD2, TXD2);
  Serial2.setTimeout(30); // 30ms máximo de espera en lectura UART para no congelar el loop

  // 3. Configuración de pines de salida para Relés y LED
  pinMode(RELAY_1_PIN, OUTPUT);
  digitalWrite(RELAY_1_PIN, RELAY_OFF);
  relay_1_activo = false;

  pinMode(RELAY_2_PIN, OUTPUT);
  digitalWrite(RELAY_2_PIN, RELAY_OFF);
  relay_2_activo = false;

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // 4. Configuración de pines analógicos
  pinMode(MQ135_PIN, INPUT);
  pinMode(SOIL_MOISTURE_PIN, INPUT);

  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println();
  Serial.println("=========================================================");
  Serial.println(" 🍓 ESP32: MONITOREO IOT + DETECCIÓN FRAGARIA (JETSON) ");
  Serial.println(" UART Jetson Nano: RX2=GPIO16, TX2=GPIO17 (115200 baud)");
  Serial.println(" Modelo Activo   : Fragaria (Fresa) - Patologías / Fruta Sana");
  Serial.println("=========================================================");

  // Inicializar sensor BMP280
  if (!bmp.begin(0x76)) {
    Serial.println("AVISO: No se encontró BMP280 en 0x76. Intentando 0x77...");
    if (!bmp.begin(0x77)) {
      Serial.println("ERROR: No se pudo detectar el BMP280.");
    }
  }

  // Conexión WiFi
  Serial.print("Conectando a WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(500);
    Serial.print(".");
    intentos++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Conectado con éxito.");
    Serial.print("Dirección IP asignada: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nNo se pudo conectar a WiFi. Modo autónomo local.");
  }
}

void loop() {
  unsigned long ahora = millis();

  // =======================================================================
  // 1. ESCUCHAR RESULTADOS POR UART DESDE LA JETSON NANO (Modelo Fragaria)
  //    (Lectura no-bloqueante ejecutada en cada iteración)
  // =======================================================================
  if (Serial2.available() > 0) {
    String lineaJetson = Serial2.readStringUntil('\n');
    lineaJetson.trim();

    if (lineaJetson.length() > 0) {
      ultimoComandoJetson = ahora;
      controlJetsonActivo = true;

      // Imprimir la trama recibida en bruto para verificación
      Serial.println("\n[Jetson Fragaria -> ESP32 UART]: " + lineaJetson);

      // --- 1. Extraer campo 'total' ---
      int totIdx = lineaJetson.indexOf("\"total\":");
      if (totIdx >= 0) {
        int endTot = lineaJetson.indexOf(",", totIdx);
        if (endTot < 0) endTot = lineaJetson.indexOf("}", totIdx);
        String totSub = lineaJetson.substring(totIdx + 8, endTot);
        totSub.trim();
        fragaria_total = totSub.toInt();
      }

      // --- 2. Extraer campo 'clase' ---
      int clsIdx = lineaJetson.indexOf("\"clase\":");
      if (clsIdx >= 0) {
        int startQuote = lineaJetson.indexOf("\"", clsIdx + 8);
        int endQuote = lineaJetson.indexOf("\"", startQuote + 1);
        if (startQuote >= 0 && endQuote > startQuote) {
          fragaria_clase = lineaJetson.substring(startQuote + 1, endQuote);
        }
      }

      // --- 3. Extraer campo 'conf' ---
      int confIdx = lineaJetson.indexOf("\"conf\":");
      if (confIdx >= 0) {
        int endConf = lineaJetson.indexOf(",", confIdx);
        if (endConf < 0) endConf = lineaJetson.indexOf("}", confIdx);
        String confSub = lineaJetson.substring(confIdx + 7, endConf);
        confSub.trim();
        fragaria_conf = confSub.toFloat();
      }

      // --- 4. Extraer campo 'enfermedad' ---
      int enfIdx = lineaJetson.indexOf("\"enfermedad\":");
      if (enfIdx >= 0) {
        int endEnf = lineaJetson.indexOf(",", enfIdx);
        if (endEnf < 0) endEnf = lineaJetson.indexOf("}", enfIdx);
        String enfSub = lineaJetson.substring(enfIdx + 13, endEnf);
        fragaria_enfermedad = (enfSub.indexOf("true") >= 0);
      }

      // ===================================================================
      // 📊 MOSTRAR EL RESULTADO DE LA DETECCIÓN EN EL MONITOR SERIAL USB
      // ===================================================================
      Serial.println("🍓 =======================================================");
      Serial.println("🍓 [NUEVA DETECCIÓN DEL MODELO FRAGARIA]");
      Serial.print("   - Total Objetos  : "); Serial.println(fragaria_total);
      Serial.print("   - Diagnóstico    : "); Serial.println(fragaria_clase);
      Serial.print("   - Confianza      : "); Serial.print(fragaria_conf * 100.0, 1); Serial.println(" %");
      Serial.print("   - Estado Sanitario: ");
      if (fragaria_total == 0) {
        Serial.println("⚪ Ninguna fruta/hoja detectada en cámara");
      } else if (fragaria_enfermedad) {
        Serial.println("⚠️  PATOLOGÍA / ENFERMEDAD DETECTADA");
      } else {
        Serial.println("✅  FRUTA / PLANTA SANA");
      }
      Serial.println("🍓 =======================================================");

      // Indicador en LED integrado: Encendido si detecta enfermedad
      digitalWrite(LED_PIN, (fragaria_total > 0 && fragaria_enfermedad) ? HIGH : LOW);

      // Confirmación UART hacia la Jetson Nano
      Serial2.println("{\"ack\": \"ok\", \"modelo\": \"fragaria\", \"recibido\": \"" + fragaria_clase + "\"}");
    }
  }

  // Comprobar si la Jetson Nano dejó de enviar datos (Timeout de 6 segundos)
  if (controlJetsonActivo && (ahora - ultimoComandoJetson > TIMEOUT_JETSON_MS)) {
    controlJetsonActivo = false;
    Serial.println("[UART] Sin datos de Fragaria desde Jetson Nano por más de 6s.");
  }

  // =======================================================================
  // 2. ENVÍO DE DATOS PERIÓDICO AL SERVIDOR FLASK EN RENDER (Cada 4 segundos)
  // =======================================================================
  if (ahora - ultimoEnvioHttp >= INTERVALO_HTTP_MS) {
    ultimoEnvioHttp = ahora;

    // Lectura de Sensores
    float temperatura = bmp.readTemperature();
    float presion = bmp.readPressure() / 100.0F; // hPa
    float altitud = bmp.readAltitude(1013.25);

    if (isnan(temperatura)) temperatura = 25.0;
    if (isnan(presion)) presion = 1013.25;
    if (isnan(altitud)) altitud = 0.0;

    int valorMQ135 = analogRead(MQ135_PIN);
    float voltajeMQ = (valorMQ135 / 4095.0) * 3.3;
    float co2_ppm = 400.0 + (voltajeMQ * 350.0);
    float humo_ppm = (voltajeMQ > 1.2) ? ((voltajeMQ - 1.2) * 20.0) : 0.0;

    int valorSuelo = analogRead(SOIL_MOISTURE_PIN);
    int humedad_suelo = map(valorSuelo, SOIL_DRY_VAL, SOIL_WET_VAL, 0, 100);
    humedad_suelo = constrain(humedad_suelo, 0, 100);

    // Imprimir en consola local USB
    Serial.println("\n----- Telemetría Actual -----");
    Serial.print("Temp: "); Serial.print(temperatura); Serial.print(" °C | ");
    Serial.print("Presión: "); Serial.print(presion); Serial.print(" hPa | ");
    Serial.print("Humedad Suelo: "); Serial.print(humedad_suelo); Serial.println("%");
    Serial.print("Relé 1: "); Serial.print(relay_1_activo ? "ENCENDIDO" : "APAGADO");
    Serial.print(" | Relé 2: "); Serial.println(relay_2_activo ? "ENCENDIDO" : "APAGADO");
    
    if (controlJetsonActivo) {
      Serial.println("[MODO]: MODELO FRAGARIA (Jetson Nano Conectada)");
      Serial.print("        Último Diagnóstico: "); Serial.print(fragaria_clase);
      Serial.print(" ("); Serial.print(fragaria_conf * 100.0, 0); Serial.println("%)");
    } else {
      Serial.println("[MODO]: SERVIDOR FLASK / AUTÓNOMO LOCAL");
    }

    // Enviar por HTTPS a Render si hay WiFi
    if (WiFi.status() == WL_CONNECTED) {
      WiFiClientSecure client;
      client.setInsecure(); // Conexión HTTPS segura sin certificados CA pesados

      HTTPClient http;
      http.begin(client, serverName);
      http.setTimeout(3500); // 3.5 segundos máximo de espera para no congelar el microcontrolador
      http.addHeader("Content-Type", "application/json");

      String jsonPayload = "{\"temperatura\":" + String(temperatura, 2) +
                           ",\"presion\":" + String(presion, 2) +
                           ",\"altitud\":" + String(altitud, 2) +
                           ",\"relay_activo\":" + (relay_1_activo ? "true" : "false") +
                           ",\"relay_2_activo\":" + (relay_2_activo ? "true" : "false") +
                           ",\"co2\":" + String(co2_ppm, 1) +
                           ",\"humo\":" + String(humo_ppm, 1) +
                           ",\"humedad_suelo\":" + String(humedad_suelo) + "}";

      int httpResponseCode = http.POST(jsonPayload);

      if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.print("Respuesta Servidor ("); Serial.print(httpResponseCode); Serial.print("): ");
        Serial.println(response);

        // Actualizar si la interfaz Web está en 'manual' o 'auto'
        int modeIdx = response.indexOf("\"mode\"");
        if (modeIdx >= 0) {
          int endMode = response.indexOf(",", modeIdx);
          if (endMode < 0) endMode = response.indexOf("}", modeIdx);
          String modeSub = response.substring(modeIdx, endMode);
          if (modeSub.indexOf("\"manual\"") >= 0) {
            modoManualWeb = true;
          } else if (modeSub.indexOf("\"auto\"") >= 0) {
            modoManualWeb = false;
          }
        }

        // Control Manual desde la Web
        if (modoManualWeb) {
          Serial.println("[ESTADO]: MODO MANUAL WEB ACTIVO");

          int r1Idx = response.indexOf("\"relay_command\"");
          if (r1Idx >= 0) {
            int endIdx = response.indexOf(",", r1Idx);
            if (endIdx < 0) endIdx = response.indexOf("}", r1Idx);
            String sub1 = response.substring(r1Idx, endIdx);
            if (sub1.indexOf("\"ON\"") >= 0) {
              digitalWrite(RELAY_1_PIN, RELAY_ON);
              relay_1_activo = true;
            } else if (sub1.indexOf("\"OFF\"") >= 0) {
              digitalWrite(RELAY_1_PIN, RELAY_OFF);
              relay_1_activo = false;
            }
          }

          int r2Idx = response.indexOf("\"relay_2_command\"");
          if (r2Idx >= 0) {
            int endIdx2 = response.indexOf(",", r2Idx);
            if (endIdx2 < 0) endIdx2 = response.indexOf("}", r2Idx);
            String sub2 = response.substring(r2Idx, endIdx2);
            if (sub2.indexOf("\"ON\"") >= 0) {
              digitalWrite(RELAY_2_PIN, RELAY_ON);
              relay_2_activo = true;
            } else if (sub2.indexOf("\"OFF\"") >= 0) {
              digitalWrite(RELAY_2_PIN, RELAY_OFF);
              relay_2_activo = false;
            }
          }
        } else {
          // En modo automático:
          if (controlJetsonActivo) {
            Serial.println("[ESTADO]: MODO AUTOMÁTICO (Supervisión Fragaria Jetson Nano Activa)");
          } else {
            Serial.println("[ESTADO]: MODO AUTOMÁTICO (Sin Jetson -> Respaldo Local Temperatura)");
            controlAutonomoLocal(temperatura);
          }
        }
      } else {
        Serial.print("Error en POST HTTP: ");
        Serial.println(httpResponseCode);
        if (!modoManualWeb && !controlJetsonActivo) {
          controlAutonomoLocal(temperatura);
        }
      }
      http.end();
    } else {
      if (!modoManualWeb && !controlJetsonActivo) {
        controlAutonomoLocal(temperatura);
      }
    }
  }

  // Pequeño retardo para no saturar el CPU del ESP32
  delay(10);
}

// Función de control autónomo local por temperatura
void controlAutonomoLocal(float temp) {
  if (temp >= 27.0) {
    if (!relay_1_activo || !relay_2_activo) {
      digitalWrite(RELAY_1_PIN, RELAY_ON);
      relay_1_activo = true;
      digitalWrite(RELAY_2_PIN, RELAY_ON);
      relay_2_activo = true;
      Serial.println("[AUTO TEMP >= 27C]: Activando relés por temperatura alta (" + String(temp, 1) + " °C)");
    }
  } else {
    if (relay_1_activo || relay_2_activo) {
      digitalWrite(RELAY_1_PIN, RELAY_OFF);
      relay_1_activo = false;
      digitalWrite(RELAY_2_PIN, RELAY_OFF);
      relay_2_activo = false;
      Serial.println("[AUTO TEMP < 27C]: Apagando relés por temperatura normal (" + String(temp, 1) + " °C)");
    }
  }
}

