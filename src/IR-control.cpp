#include "IR-control.h"
#include "motor_control.h"
#include <math.h>

static constexpr int IR_ACTIVE_LEVEL = LOW;
static constexpr int IR_DIRECTIONS_DEG[IR_SENSOR_COUNT] = {0, 30, 90, 270, 330, 180};
static constexpr unsigned long IR_LOST_HOLD_MS = 120;
static constexpr int IR_STABLE_THRESHOLD = 2;
static constexpr int IR_PRINT_INTERVAL_MS = 150;
static constexpr float PI_F = 3.14159265358979323846f;

// 选择6个GPIO作为红外输入（可根据实际连线调整）
const int IR_PINS[IR_SENSOR_COUNT] = {4, 5, 6, 7, 8, 9};

// 方向名称数组，按引脚顺序对应，和实际安装布局一致
static const char* IR_DIRECTIONS[IR_SENSOR_COUNT] = {
    "0°",   // GPIO4
    "30°",  // GPIO5
    "90°", // GPIO6
    "270°", // GPIO7
    "330°", // GPIO8
    "180°"  // GPIO9
};

struct IRAnalysis {
    bool hasSignal;
    int mainIndex;
    int errorDeg;
    int activeCount;
};

static int normalizeAngle(int angle) {
    while (angle > 180) angle -= 360;
    while (angle < -180) angle += 360;
    return angle;
}

static IRAnalysis analyzeIRSignal(const int irVals[IR_SENSOR_COUNT]) {
    IRAnalysis analysis = {false, -1, 0, 0};
    int activeIdx[IR_SENSOR_COUNT];
    int count = 0;
    float vectorX = 0.0f;
    float vectorY = 0.0f;

    for (int i = 0; i < IR_SENSOR_COUNT; ++i) {
        if (irVals[i] == IR_ACTIVE_LEVEL) {
            activeIdx[count++] = i;
            float rad = IR_DIRECTIONS_DEG[i] * PI_F / 180.0f;
            float weight = 1.0f;
            if (i == 0 || i == 1 || i == 5) {
                weight = 1.25f;
            }
            vectorX += cosf(rad) * weight;
            vectorY += sinf(rad) * weight;
        }
    }

    if (count == 0) {
        return analysis;
    }

    int filtered[IR_SENSOR_COUNT];
    int filteredCount = 0;
    bool front = (irVals[0] == IR_ACTIVE_LEVEL || irVals[1] == IR_ACTIVE_LEVEL || irVals[5] == IR_ACTIVE_LEVEL);
    if (front) {
        for (int i = 0; i < count; ++i) {
            if (activeIdx[i] != 2 && activeIdx[i] != 3 && activeIdx[i] != 4) {
                filtered[filteredCount++] = activeIdx[i];
            }
        }
    }
    if (filteredCount > 0) {
        count = filteredCount;
        for (int i = 0; i < count; ++i) {
            activeIdx[i] = filtered[i];
        }
    }

    int mainIdx = activeIdx[count / 2];
    float angleDeg = atan2f(vectorY, vectorX) * 180.0f / PI_F;
    analysis.hasSignal = true;
    analysis.mainIndex = mainIdx;
    analysis.errorDeg = normalizeAngle(static_cast<int>(lroundf(angleDeg)));
    analysis.activeCount = count;
    return analysis;
}

void setupIR() {
    for (int i = 0; i < IR_SENSOR_COUNT; ++i) {
        pinMode(IR_PINS[i], INPUT_PULLUP);
    }
    Serial.println("IR输入引脚初始化完成");
}

// 判断主方向（前方优先，取中间，抑制反射；红外触发为低电平）
int getMainIRDirection(const int irVals[IR_SENSOR_COUNT]) {
    return analyzeIRSignal(irVals).mainIndex;
}

// 状态变量用于方向切换防抖
void handleIRSignal() {
    static int lastMainDir = -1;
    static int stableMainDir = -1;
    static int stableCount = 0;
    static unsigned long lastOutputMs = 0;
    static unsigned long lastSignalMs = 0;

    int irVals[IR_SENSOR_COUNT];
    for (int i = 0; i < IR_SENSOR_COUNT; ++i) {
        irVals[i] = digitalRead(IR_PINS[i]);
    }
    IRAnalysis analysis = analyzeIRSignal(irVals);
    int mainDir = analysis.mainIndex;

    if (analysis.hasSignal) {
        lastSignalMs = millis();
        if (mainDir == lastMainDir) {
            stableCount++;
        } else {
            stableCount = 1;
            lastMainDir = mainDir;
        }
        if (stableCount >= IR_STABLE_THRESHOLD) {
            if (mainDir != stableMainDir || millis() - lastOutputMs >= IR_PRINT_INTERVAL_MS) {
                Serial.print("主方向: ");
                Serial.print(IR_DIRECTIONS[mainDir]);
                Serial.print(" , 偏差: ");
                Serial.print(analysis.errorDeg);
                Serial.print("° , 激活: ");
                Serial.println(analysis.activeCount);
                lastOutputMs = millis();
            }

            stableMainDir = mainDir;
                motor_control_ir_navigation(analysis.errorDeg, false);
        }
    } else {
        if (millis() - lastSignalMs > IR_LOST_HOLD_MS) {
            stableCount = 0;
            lastMainDir = -1;
            stableMainDir = -1;
            motor_control_ir_navigation(-1, true);
        }
    }
}
