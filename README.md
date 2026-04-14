# Smart Boat Navigation 智能船舶导航系统

![项目状态](https://img.shields.io/badge/状态-本地红外控制-brightgreen)
![版本](https://img.shields.io/badge/版本-0.6.0-blue)
![平台](https://img.shields.io/badge/平台-ESP32S3-orange)

## 项目简介

当前版本面向 C1-1 智能航行赛制，已经收敛为本地红外控制方案。系统不再依赖 Wi-Fi、MQTT、摄像头网络推流或网页控制，全部控制逻辑在 ESP32 本地完成。

详细设计说明见 [C1-1 本地红外控制说明](docs/c1-1-local-ir-control.md)。
汇报使用版本见 [C1-1 智能船舶项目汇报说明](docs/c1-1-项目汇报说明.md)。

## 现在的功能

- 6 路红外输入，触发为低电平，空闲为高电平
- 红外信号稳定判定，减少抖动误触发
- 双电机差速控制转向
- 红外信号丢失后的短时保持与停车保护
- 旧版本代码已备份，便于对比和回退

## 硬件与软件

- 硬件平台：ESP32-S3
- 开发环境：PlatformIO + Visual Studio Code
- 控制方式：本地串口调试 + 红外输入 + PWM 电机输出
- 网络能力：已移除

## 文件说明

- [src/main.cpp](src/main.cpp)：程序入口，只负责初始化红外和电机。
- [src/IR-control.cpp](src/IR-control.cpp)：红外读取、方向判定、偏差计算。
- [src/motor_control.cpp](src/motor_control.cpp)：双电机差速输出和限速控制。
- [docs/c1-1-local-ir-control.md](docs/c1-1-local-ir-control.md)：C1-1 中文说明文档。

## 编译与上传

1. 安装 PlatformIO。
2. 打开工程目录。
3. 编译并上传到开发板：`pio run --target upload`。

## 说明

如果你还想保留历史版本，旧文件已备份到 [backup/2026-04-11_C1-1_before_opt](backup/2026-04-11_C1-1_before_opt)。

## 许可证

MIT License
