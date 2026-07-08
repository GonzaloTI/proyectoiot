#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <WiFi.h>
#include <HTTPClient.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define RELAY_PIN 4 // Pin GPIO al que se conecta el pin 'IN' del relé
#define MQ135_PIN 34 // Pin analógico (GPIO 34) al que se conecta el pin 'AO' del MQ-135

// NOTA: La mayoría de módulos de relé comerciales para Arduino son de lógica inversa (se activan con LOW).
// Si tu relé se activa con nivel ALTO, cambia RELAY_ON a HIGH y RELAY_OFF a LOW.
#define RELAY_ON LOW
#define RELAY_OFF HIGH

// Configuración de Red WiFi (Reemplaza con tus datos)
const char* ssid = "gonzalo";
const char* password = "1234567899";

// Dirección IP del servidor Flask (Reemplaza con la IP de tu computadora)
const char* serverName = "http://10.86.129.92:5000/api/datos";

Adafruit_BMP280 bmp;
bool relay_activo = false;

void setup() {
  Serial.begin(115200);

  // Configuración del pin del relé
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, RELAY_OFF); // Inicialmente apagado
  relay_activo = false;

  // Configuración del pin analógico del MQ-135
  pinMode(MQ135_PIN, INPUT);

  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println();
  Serial.println("Inicializando BMP280...");

  if (!bmp.begin(0x76)) {
    Serial.println("ERROR: No se encontró el BMP280.");
    while (1);
  }
  Serial.print("Chip ID: 0x");
  Serial.println(bmp.sensorID(), HEX);
  Serial.println("BMP280 detectado correctamente.");

  // Conexión WiFi
  Serial.print("Conectando a WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  
  // Esperar a que se conecte
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("");
    Serial.println("Conexión WiFi establecida.");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("");
    Serial.println("No se pudo conectar al WiFi. Iniciando en modo local autónomo.");
  }
}

void loop() {
  float temperatura = bmp.readTemperature();
  float presion     = bmp.readPressure() / 100.0F;   // hPa
  float altitud     = bmp.readAltitude(1013.25);     // metros

  // Leer sensor de calidad de aire MQ-135 en GPIO 34
  int raw_mq = analogRead(MQ135_PIN);
  
  // Fórmulas de estimación: el MQ-135 tiene base de 400 PPM de CO2 en aire limpio
  float co2_ppm = 400.0 + ((float)raw_mq * 0.4);
  // El humo se activa por encima de un umbral base (ej: 700 ADC)
  float humo_ppm = (raw_mq > 700) ? ((float)(raw_mq - 700) * 0.3) : 0.0;

  Serial.println("=================================");
  Serial.print("Temperatura : ");
  Serial.print(temperatura, 2);
  Serial.println(" °C");
  Serial.print("Presión     : ");
  Serial.print(presion, 2);
  Serial.println(" hPa");
  Serial.print("Altitud     : ");
  Serial.print(altitud, 2);
  Serial.println(" m");
  Serial.print("CO2 (PPM)   : ");
  Serial.print(co2_ppm, 1);
  Serial.println(" ppm");
  Serial.print("Humo (PPM)  : ");
  Serial.print(humo_ppm, 1);
  Serial.println(" ppm");
  Serial.print("ADC MQ-135  : ");
  Serial.println(raw_mq);

  // Si estamos conectados a WiFi, enviamos datos al servidor
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    // Construimos el payload JSON directamente como String con CO2 y Humo
    String jsonPayload = "{\"temperatura\":" + String(temperatura, 2) + 
                         ",\"presion\":" + String(presion, 2) + 
                         ",\"altitud\":" + String(altitud, 2) + 
                         ",\"relay_activo\":" + (relay_activo ? "true" : "false") + 
                         ",\"co2\":" + String(co2_ppm, 1) + 
                         ",\"humo\":" + String(humo_ppm, 1) + "}";

    Serial.println("Enviando datos al servidor...");
    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("Respuesta de API (");
      Serial.print(httpResponseCode);
      Serial.print("): ");
      Serial.println(response);

      // Determinar si el servidor nos indica usar el modo manual o automático
      int modeIdx = response.indexOf("\"mode\"");
      bool manualMode = false;
      if (modeIdx >= 0) {
        String modeSub = response.substring(modeIdx);
        if (modeSub.indexOf("\"manual\"") >= 0) {
          manualMode = true;
        }
      }

      if (manualMode) {
        // MODO MANUAL: El servidor decide el estado
        int relayCmdIdx = response.indexOf("\"relay_command\"");
        if (relayCmdIdx >= 0) {
          String sub = response.substring(relayCmdIdx);
          if (sub.indexOf("\"ON\"") >= 0) {
            digitalWrite(RELAY_PIN, RELAY_ON);
            relay_activo = true;
            Serial.println("Modo: MANUAL | Comando Servidor: ENCENDER");
          } else if (sub.indexOf("\"OFF\"") >= 0) {
            digitalWrite(RELAY_PIN, RELAY_OFF);
            relay_activo = false;
            Serial.println("Modo: MANUAL | Comando Servidor: APAGAR");
          }
        }
      } else {
        // MODO AUTOMÁTICO (Local): El ESP32 decide según su propia temperatura
        controlAutonomoLocal(temperatura);
        Serial.println("Modo: AUTOMÁTICO (Control Local)");
      }
    } else {
      Serial.print("Error en petición HTTP: ");
      Serial.println(httpResponseCode);
      
      // Control de respaldo en caso de fallo en la llamada HTTP -> MODO AUTOMÁTICO LOCAL
      controlAutonomoLocal(temperatura);
      Serial.println("Error HTTP. Modo: AUTOMÁTICO (Respaldo Local)");
    }
    http.end();
  } else {
    // Si no hay conexión WiFi -> MODO AUTOMÁTICO LOCAL
    controlAutonomoLocal(temperatura);
    Serial.println("WiFi desconectado. Modo: AUTOMÁTICO (Respaldo Local)");
  }

  Serial.print("Estado Relé : ");
  Serial.println(relay_activo ? "ACTIVADO" : "DESACTIVADO");
  Serial.println("=================================\n");

  delay(2000); // Enviar datos cada 2 segundos
}

// Función de respaldo para control local autónomo
void controlAutonomoLocal(float temp) {
  if (temp >= 27.0) {
    digitalWrite(RELAY_PIN, RELAY_ON);
    relay_activo = true;
  } else {
    digitalWrite(RELAY_PIN, RELAY_OFF);
    relay_activo = false;
  }
}