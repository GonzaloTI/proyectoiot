/*
 * ============================================================================
 * Proyecto: Comunicación Serial UART entre ESP32 y NVIDIA Jetson Nano (P3541)
 * Archivo:  detector_dedos_esp32_uart.ino
 * ============================================================================
 * Conexión física directa con la serigrafía de tu Jetson Nano P3541:
 *   - ESP32 GPIO 16 (RX2) <--- Conectar a Pin 8  'D14 (TXD)' de la Jetson Nano
 *   - ESP32 GPIO 17 (TX2) ---> Conectar a Pin 10 'D15 (RXD)' de la Jetson Nano
 *   - ESP32 GND           <---> Conectar a Pin 6, 9 o 14 'GND' de la Jetson Nano
 *
 * Conexión de Relés:
 *   - Relé 1 (Activado con Dedo Índice): GPIO 4
 *   - Relé 2 (Activado con Dedo Medio) : GPIO 5
 * ============================================================================
 */

#define RXD2 16
#define TXD2 17
#define LED_PIN 2     // LED integrado

#define RELAY_1_PIN 4 // Pin Relé 1 (Índice)
#define RELAY_2_PIN 5 // Pin Relé 2 (Medio)

#define RELAY_ON LOW
#define RELAY_OFF HIGH

bool relay_1_activo = false;
bool relay_2_activo = false;

unsigned long previousMillis = 0;
const long interval = 1000;  // Intervalo de envío de telemetría (1 segundo)
int messageCounter = 0;

void setup() {
  // 1. Monitor serial USB PC
  Serial.begin(115200);
  delay(100);

  // 2. Puerto Serial2 para comunicarse con Jetson Nano (P3541)
  Serial2.begin(115200, SERIAL_8N1, RXD2, TXD2);

  // 3. Configurar pines de LED y Relés
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  pinMode(RELAY_1_PIN, OUTPUT);
  digitalWrite(RELAY_1_PIN, RELAY_OFF);
  relay_1_activo = false;

  pinMode(RELAY_2_PIN, OUTPUT);
  digitalWrite(RELAY_2_PIN, RELAY_OFF);
  relay_2_activo = false;

  Serial.println("==================================================");
  Serial.println("ESP32 UART DEMO: RELÉS POR DEDOS");
  Serial.println("RX2 = GPIO 16 (Pin 8 Jetson), TX2 = GPIO 17 (Pin 10 Jetson)");
  Serial.println("Relé 1: GPIO 4 | Relé 2: GPIO 5");
  Serial.println("==================================================");
}

void loop() {
  unsigned long currentMillis = millis();

  // -------------------------------------------------------------
  // 1. Enviar telemetría periódica hacia la Jetson Nano
  // -------------------------------------------------------------
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;
    messageCounter++;

    float simulatedTemp = 24.0 + (random(-20, 20) / 10.0);
    String telemetry = "TEMP:" + String(simulatedTemp, 2) + ",COUNT:" + String(messageCounter) +
                       ",R1:" + String(relay_1_activo ? "1" : "0") +
                       ",R2:" + String(relay_2_activo ? "1" : "0");

    Serial2.println(telemetry);
    Serial.println("[ESP32 -> Jetson]: " + telemetry);
  }

  // -------------------------------------------------------------
  // 2. Escuchar y procesar comandos recibidos desde la Jetson Nano
  // -------------------------------------------------------------
  if (Serial2.available() > 0) {
    String command = Serial2.readStringUntil('\n');
    command.trim();

    if (command.length() > 0) {
      Serial.println("[Jetson -> ESP32]: " + command);

      // Parsear comando JSON de activación de relés
      int r1Idx = command.indexOf("\"relay_command\"");
      int r2Idx = command.indexOf("\"relay_2_command\"");

      if (r1Idx >= 0 || r2Idx >= 0) {
        // Control Relé 1 (Índice)
        if (r1Idx >= 0) {
          int endR1 = command.indexOf(",", r1Idx);
          if (endR1 < 0) endR1 = command.indexOf("}", r1Idx);
          String sub1 = command.substring(r1Idx, endR1);
          if (sub1.indexOf("\"ON\"") >= 0) {
            digitalWrite(RELAY_1_PIN, RELAY_ON);
            relay_1_activo = true;
          } else if (sub1.indexOf("\"OFF\"") >= 0) {
            digitalWrite(RELAY_1_PIN, RELAY_OFF);
            relay_1_activo = false;
          }
        }

        // Control Relé 2 (Medio)
        if (r2Idx >= 0) {
          int endR2 = command.indexOf(",", r2Idx);
          if (endR2 < 0) endR2 = command.indexOf("}", r2Idx);
          String sub2 = command.substring(r2Idx, endR2);
          if (sub2.indexOf("\"ON\"") >= 0) {
            digitalWrite(RELAY_2_PIN, RELAY_ON);
            relay_2_activo = true;
          } else if (sub2.indexOf("\"OFF\"") >= 0) {
            digitalWrite(RELAY_2_PIN, RELAY_OFF);
            relay_2_activo = false;
          }
        }

        digitalWrite(LED_PIN, (relay_1_activo || relay_2_activo) ? HIGH : LOW);
        Serial2.println("ACK: R1=" + String(relay_1_activo ? "ON" : "OFF") +
                        " R2=" + String(relay_2_activo ? "ON" : "OFF"));
      }
      else if (command == "LED_ON") {
        digitalWrite(LED_PIN, HIGH);
        Serial2.println("ACK: LED_ON_OK");
      } 
      else if (command == "LED_OFF") {
        digitalWrite(LED_PIN, LOW);
        Serial2.println("ACK: LED_OFF_OK");
      } 
      else if (command == "PING") {
        Serial2.println("ACK: PONG");
      } 
      else {
        Serial2.println("ERR: UNKNOWN_COMMAND (" + command + ")");
      }
    }
  }
}
