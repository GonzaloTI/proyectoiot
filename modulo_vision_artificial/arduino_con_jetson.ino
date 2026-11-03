/*
 * =========================================================================================
 * Proyecto: Monitoreo IoT + Control de Relés por Visión Artificial (Jetson Nano + ESP32)
 * Archivo:  arduino_con_jetson.ino
 * =========================================================================================
 * Conexión física directa con NVIDIA Jetson Nano (Conector 40 Pines):
 *   - ESP32 GPIO 16 (RX2) <--- Conectar a Pin 8  'D14 (TXD)' de la Jetson Nano
 *   - ESP32 GPIO 17 (TX2) ---> Conectar a Pin 10 'D15 (RXD)' de la Jetson Nano
 *   - ESP32 GND           <---> Conectar a Pin 6, 9 o 14 'GND' de la Jetson Nano
 *
 * Conexión de Relés:
 *   - Relé 1 (Controlado por Dedo Índice): GPIO 4
 *   - Relé 2 (Controlado por Dedo Medio) : GPIO 5
 *
 * Sensores conectados a ESP32:
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
#define RELAY_1_PIN 4 // Pin GPIO para Relé 1 (Dedo Índice)
#define RELAY_2_PIN 5 // Pin GPIO para Relé 2 (Dedo Medio)
#define LED_PIN 2     // LED integrado en ESP32

// Lógica de activación de relé:
// NOTA IMPORTANTE:
// - La mayoría de módulos relé para Arduino/ESP32 se activan con nivel BAJO (LOW).
// - Si tu módulo relé se activa con nivel ALTO (o tiene el jumper en 'H'), cambia:
//     #define RELAY_ON  HIGH
//     #define RELAY_OFF LOW
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

// --- Dirección IP del Servidor Flask ---
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
const unsigned long TIMEOUT_JETSON_MS = 6000; // Margen de 6 segundos sin comandos de Jetson 

// Temporizador no bloqueante para envío HTTP a Flask (cada 4 segundos para no saturar CPU con SSL)
unsigned long ultimoEnvioHttp = 0;
const unsigned long INTERVALO_HTTP_MS = 4000;

void setup() {
  // 1. Inicializar Serial USB (para depurar en PC)
  Serial.begin(115200);

  // 2. Inicializar Serial2 para comunicación UART con Jetson Nano (con timeout corto para no bloquear)
  Serial2.begin(115200, SERIAL_8N1, RXD2, TXD2);
  Serial2.setTimeout(30); // 30ms max de espera en lectura UART

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
  Serial.println(" ESP32 DEMO: IOT + CONTROL RELÉS POR VISIÓN ARTIFICIAL");
  Serial.println(" UART Jetson Nano: RX2=GPIO16, TX2=GPIO17 (115200 baud)");
  Serial.println(" Pines de Relés : Relé 1 = GPIO 4 | Relé 2 = GPIO 5");
  Serial.print(" Nivel de Activación: ");
  Serial.println(RELAY_ON == LOW ? "NIVEL BAJO (LOW)" : "NIVEL ALTO (HIGH)");
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
  // 1. ESCUCHAR COMANDOS POR UART DESDE LA JETSON NANO (Visión Artificial)
  //    (Se ejecuta en cada ciclo, con respuesta inmediata < 15ms)
  // =======================================================================
  if (Serial2.available() > 0) {
    String comandoJetson = Serial2.readStringUntil('\n');
    comandoJetson.trim();

    if (comandoJetson.length() > 0) {
      Serial.println("[Jetson -> ESP32 UART]: " + comandoJetson);
      ultimoComandoJetson = ahora;
      controlJetsonActivo = true;

      // =====================================================================
      // PRIORIDAD DE CONTROL:
      // Si la interfaz Web está en 'Modo Manual', la Web manda y la Jetson no
      // puede apagar ni alterar los relés.
      // Si la interfaz Web está en 'Modo Automático', la Jetson Nano controla
      // los relés por Visión Artificial (dedos levantados).
      // =====================================================================
      if (modoManualWeb) {
        Serial.println("[PRIORIDAD]: Modo Manual activo en Web. Ignorando comando de Jetson Nano.");
      } else {
        // --- Procesar comando para Relé 1 (Dedo Índice) ---
        int r1Idx = comandoJetson.indexOf("\"relay_command\"");
        if (r1Idx >= 0) {
          int endR1 = comandoJetson.indexOf(",", r1Idx);
          if (endR1 < 0) endR1 = comandoJetson.indexOf("}", r1Idx);
          String sub1 = comandoJetson.substring(r1Idx, endR1);
          if (sub1.indexOf("\"ON\"") >= 0) {
            digitalWrite(RELAY_1_PIN, RELAY_ON);
            relay_1_activo = true;
            Serial.println("[JETSON UART] >>> RELE 1 ENCENDIDO (GPIO 4 = " + String(RELAY_ON == LOW ? "LOW" : "HIGH") + ")");
          } else if (sub1.indexOf("\"OFF\"") >= 0) {
            digitalWrite(RELAY_1_PIN, RELAY_OFF);
            relay_1_activo = false;
            Serial.println("[JETSON UART] >>> RELE 1 APAGADO (GPIO 4 = " + String(RELAY_OFF == LOW ? "LOW" : "HIGH") + ")");
          }
        }

        // --- Procesar comando para Relé 2 (Dedo Medio) ---
        int r2Idx = comandoJetson.indexOf("\"relay_2_command\"");
        if (r2Idx >= 0) {
          int endR2 = comandoJetson.indexOf(",", r2Idx);
          if (endR2 < 0) endR2 = comandoJetson.indexOf("}", r2Idx);
          String sub2 = comandoJetson.substring(r2Idx, endR2);
          if (sub2.indexOf("\"ON\"") >= 0) {
            digitalWrite(RELAY_2_PIN, RELAY_ON);
            relay_2_activo = true;
            Serial.println("[JETSON UART] >>> RELE 2 ENCENDIDO (GPIO 5 = " + String(RELAY_ON == LOW ? "LOW" : "HIGH") + ")");
          } else if (sub2.indexOf("\"OFF\"") >= 0) {
            digitalWrite(RELAY_2_PIN, RELAY_OFF);
            relay_2_activo = false;
            Serial.println("[JETSON UART] >>> RELE 2 APAGADO (GPIO 5 = " + String(RELAY_OFF == LOW ? "LOW" : "HIGH") + ")");
          }
        }

        // Encender LED integrado si al menos 1 relé está activo
        digitalWrite(LED_PIN, (relay_1_activo || relay_2_activo) ? HIGH : LOW);
      }

      // Enviar confirmación UART hacia Jetson Nano
      Serial2.println("{\"ack\": \"ok\", \"r1\": " + String(relay_1_activo ? "1" : "0") +
                      ", \"r2\": " + String(relay_2_activo ? "1" : "0") + "}");
    }
  }

  // Comprobar si Jetson Nano dejó de enviar datos (Timeout)
  if (controlJetsonActivo && (ahora - ultimoComandoJetson > TIMEOUT_JETSON_MS)) {
    controlJetsonActivo = false;
    Serial.println("[UART] Timeout de Jetson Nano. Liberando relés para control Servidor/Autónomo.");
  }

  // =======================================================================
  // 2. ENVÍO DE DATOS PERIÓDICO AL SERVIDOR FLASK (Cada 2 segundos)
  // =======================================================================
  if (ahora - ultimoEnvioHttp >= INTERVALO_HTTP_MS) {
    ultimoEnvioHttp = ahora;

    // Lectura de Sensores
    float temperatura = bmp.readTemperature();
    float presion = bmp.readPressure() / 100.0F; // hPa
    float altitud = bmp.readAltitude(1013.25);

    // Si el sensor no responde adecuadamente, valores seguros por defecto
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
      Serial.println("[MODO]: GESTOS JETSON NANO (Visión Artificial)");
    } else {
      Serial.println("[MODO]: SERVIDOR FLASK / AUTÓNOMO LOCAL");
    }

    // Enviar por HTTPS a Render si hay WiFi
    if (WiFi.status() == WL_CONNECTED) {
      WiFiClientSecure client;
      client.setInsecure(); // Conexión HTTPS segura sin validación estricta de certificados CA

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

        // ===================================================================
        // 1. SI LA WEB ESTÁ EN 'MODO MANUAL':
        //    Los botones de la página Web tienen el control absoluto.
        // ===================================================================
        if (modoManualWeb) {
          Serial.println("[ESTADO]: MODO MANUAL WEB ACTIVO (Manda la Web)");

          // Relé 1 desde Flask
          int r1Idx = response.indexOf("\"relay_command\"");
          if (r1Idx >= 0) {
            int endIdx = response.indexOf(",", r1Idx);
            if (endIdx < 0) endIdx = response.indexOf("}", r1Idx);
            String sub1 = response.substring(r1Idx, endIdx);
            if (sub1.indexOf("\"ON\"") >= 0) {
              digitalWrite(RELAY_1_PIN, RELAY_ON);
              relay_1_activo = true;
              Serial.println("[WEB FLASK] >>> RELE 1 ENCENDIDO (GPIO 4)");
            } else if (sub1.indexOf("\"OFF\"") >= 0) {
              digitalWrite(RELAY_1_PIN, RELAY_OFF);
              relay_1_activo = false;
              Serial.println("[WEB FLASK] >>> RELE 1 APAGADO (GPIO 4)");
            }
          }

          // Relé 2 desde Flask
          int r2Idx = response.indexOf("\"relay_2_command\"");
          if (r2Idx >= 0) {
            int endIdx2 = response.indexOf(",", r2Idx);
            if (endIdx2 < 0) endIdx2 = response.indexOf("}", r2Idx);
            String sub2 = response.substring(r2Idx, endIdx2);
            if (sub2.indexOf("\"ON\"") >= 0) {
              digitalWrite(RELAY_2_PIN, RELAY_ON);
              relay_2_activo = true;
              Serial.println("[WEB FLASK] >>> RELE 2 ENCENDIDO (GPIO 5)");
            } else if (sub2.indexOf("\"OFF\"") >= 0) {
              digitalWrite(RELAY_2_PIN, RELAY_OFF);
              relay_2_activo = false;
              Serial.println("[WEB FLASK] >>> RELE 2 APAGADO (GPIO 5)");
            }
          }

          // Actualizar LED
          digitalWrite(LED_PIN, (relay_1_activo || relay_2_activo) ? HIGH : LOW);

        } else {
          // ===================================================================
          // 2. SI LA WEB ESTÁ EN 'MODO AUTOMÁTICO':
          //    Manda la Visión Artificial de la Jetson Nano.
          //    Solo si la Jetson no está enviando nada, actúa el sensor de temp.
          // ===================================================================
          if (controlJetsonActivo) {
            Serial.println("[ESTADO]: MODO AUTOMÁTICO (Gobernado por Visión Artificial de Jetson)");
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

