#ifndef IR_CONTROL_H
#define IR_CONTROL_H

#define IR_SENSOR_COUNT 6

// IR传感器引脚声明，触发时为低电平，空闲时为高电平
extern const int IR_PINS[IR_SENSOR_COUNT];

// 初始化红外接收器
void setupIR();

// 根据当前红外输入获取主方向索引
int getMainIRDirection(const int irVals[IR_SENSOR_COUNT]);

// 处理红外信号并控制电机
void handleIRSignal();

#endif // IR_CONTROL_H
