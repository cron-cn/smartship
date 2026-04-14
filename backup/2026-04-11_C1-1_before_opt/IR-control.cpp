#include "IR-control.h"
#include "motor_control.h"

static constexpr int IR_ACTIVE_LEVEL = LOW;

// 选择6个GPIO作为红外输入（可根据实际连线调整）
const int IR_PINS[IR_SENSOR_COUNT] = {4, 5, 6, 7, 8, 9};

// 方向名称数组，按引脚顺序对应
static const char* IR_DIRECTIONS[IR_SENSOR_COUNT] = {
    "0°",   // GPIO4
    "60°",  // GPIO5
    "90°", // GPIO6
    "270°", // GPIO7
    "330°", // GPIO8
    "180°"  // GPIO9
};

void setupIR() {
    for (int i = 0; i < IR_SENSOR_COUNT; ++i) {
        pinMode(IR_PINS[i], INPUT_PULLUP);
    }
    Serial.println("IR输入引脚初始化完成");
}

// 判断主方向（前方优先，取中间，抑制反射；红外触发为低电平）
int getMainIRDirection(const int irVals[IR_SENSOR_COUNT]) {
    int activeIdx[IR_SENSOR_COUNT], count = 0;
    for (int i = 0; i < IR_SENSOR_COUNT; ++i) {
        if (irVals[i] == IR_ACTIVE_LEVEL) activeIdx[count++] = i;
    }
    if (count == 0) return -1; // 无信号
    // 前方优先：0,1,5有信号时，忽略2,3,4
    bool front = (irVals[0] == IR_ACTIVE_LEVEL || irVals[1] == IR_ACTIVE_LEVEL || irVals[5] == IR_ACTIVE_LEVEL);
    if (front) {
        int filtered[IR_SENSOR_COUNT], fcount = 0;
        for (int i = 0; i < count; ++i) {
            if (activeIdx[i] != 2 && activeIdx[i] != 3 && activeIdx[i] != 4)
                filtered[fcount++] = activeIdx[i];
        }
        if (fcount > 0) {
            count = fcount;
            for (int i = 0; i < count; ++i) activeIdx[i] = filtered[i];
        }
    }
    // 取中间那个
    int mainIdx = activeIdx[count/2];
    return mainIdx;
}

// 状态变量用于方向切换防抖
void handleIRSignal() {
    static int lastMainDir = -1;
    static int stableMainDir = -1;
    static int stableCount = 0;
    const int STABLE_THRESHOLD = 3; // 连续3帧一致才判定为新方向

    int irVals[IR_SENSOR_COUNT];
    for (int i = 0; i < IR_SENSOR_COUNT; ++i) {
        irVals[i] = digitalRead(IR_PINS[i]);
    }
    int mainDir = getMainIRDirection(irVals);

    if (mainDir >= 0) {
        if (mainDir == lastMainDir) {
            stableCount++;
        } else {
            stableCount = 1;
            lastMainDir = mainDir;
        }
        // 只有连续多帧一致且与上次输出方向不同才输出
        if (stableCount >= STABLE_THRESHOLD && mainDir != stableMainDir) {
            Serial.print("主方向: ");
            Serial.print(IR_DIRECTIONS[mainDir]);
            Serial.print(" (");
            bool first = true;
            for (int i = 0; i < IR_SENSOR_COUNT; ++i) {
                if (irVals[i] == IR_ACTIVE_LEVEL) {
                    if (!first) Serial.print(" ");
                    Serial.print(IR_PINS[i]);
                    first = false;
                }
            }
            Serial.println(")");

            stableMainDir = mainDir;
            motor_control_ir_navigation(mainDir, false);
        }
        else if (stableCount >= STABLE_THRESHOLD && mainDir == stableMainDir) {
            motor_control_ir_navigation(mainDir, false);
        }
    } else {
        stableCount = 0;
        lastMainDir = -1;
        stableMainDir = -1;
        motor_control_ir_navigation(-1, true);
    }
}
