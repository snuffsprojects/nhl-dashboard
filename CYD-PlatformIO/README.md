# VGK CYD Pilot

PlatformIO pilot firmware for the 320×240 ESP32-2432S028R Cheap Yellow Display.
It is separate from `CYD-Board-Software/cyd_board.ino`, which remains the known
rollback firmware.

## Prepare on the workstation

1. Copy this whole folder to the machine with the spare CYD attached.
2. Open the folder in a **local** VS Code window with PlatformIO installed.
3. Copy `include/secrets.example.h` to `include/secrets.h`, then enter the development Wi-Fi details and Pi address.
4. Use **PlatformIO: Build**.
5. Select the CYD serial port and use **PlatformIO: Upload**.
6. Open the serial monitor at 115200 baud.

## Pilot controls

The BOOT button cycles through local demonstration screens:

1. Live
2. Final
3. Countdown
4. Goal
5. Offline
6. Resume the real MQTT feed

Set `ENABLE_DEMO_BUTTON=0` in `platformio.ini` for the eventual production build.

## Rollback

The original sketch is untouched at `../CYD-Board-Software/cyd_board.ino`.
