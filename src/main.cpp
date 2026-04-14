#include <Arduino.h>
#include "motor_control.h"
#include "IR-control.h"

// --- Arduino Setup ---
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\n\n====================================");
  Serial.println("      船舶本地红外驱动启动中...     ");
  Serial.println("====================================");

  // 初始化红外接收器
  Serial.println("初始化红外接收器...");
  setupIR();

  // 初始化电机
  setup_motors();

  Serial.println("====================================");
  Serial.println("       本地红外控制模式已就绪!          ");
  Serial.println("====================================");
}

// --- Arduino Loop ---
void loop() {
  handleIRSignal();
  delay(2);
}
