#!/usr/bin/env python3
"""
ESLab HW3 - BLE Central on Raspberry Pi (bleak 版本)

bleak 走 BlueZ 的 D-Bus 介面，在新版 Raspberry Pi OS 上比 bluepy 穩定。

功能：
  1. 掃描並找到名稱含關鍵字的裝置（例如 iPhone LightBlue 的 "Health Thermometer"）
  2. 連線並列出所有 Service / Characteristic / Descriptor
  3. 對目標 characteristic 做 read / write
  4. 開啟 Indication -> BlueZ 會把該 characteristic 的 CCCD (0x2902) 寫成 0x0002
     （目標 characteristic 只有 Indicate、沒有 Notify 時，寫的一定是 0x0002）
  5. 等待手機送來的 indication 並印出
  6. 結束前關閉 indication -> CCCD 寫回 0x0000，然後斷線

用法：
  python3 ble_central_bleak.py Thermometer 2a1c
     第 1 個參數：裝置名稱關鍵字
     第 2 個參數：目標 characteristic UUID 關鍵字（2a1c = Temperature Measurement）
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

SCAN_SECONDS = 15
LISTEN_SECONDS = 60


def on_indication(sender, data: bytearray):
    print(f"[RX] from {sender.uuid}  hex={data.hex(' ')}  raw={bytes(data)!r}")


async def main():
    name_kw = (sys.argv[1] if len(sys.argv) > 1 else "Thermometer").lower()
    uuid_kw = (sys.argv[2] if len(sys.argv) > 2 else "2a1c").lower()

    print(f"Scanning up to {SCAN_SECONDS} s for a device whose name contains '{name_kw}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: name_kw in ((adv.local_name or d.name or "").lower()),
        timeout=SCAN_SECONDS,
    )
    if device is None:
        print("Device not found. Is the phone app in the foreground and advertising?")
        return
    print(f"Found {device.address}  {device.name}")

    async with BleakClient(device, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}")

        # --- 列出 GATT 資料庫 ---
        print("\n========== GATT database ==========")
        target = None
        for svc in client.services:
            print(f"Service {svc.uuid}  ({svc.description})")
            for ch in svc.characteristics:
                print(f"  Char  handle={ch.handle:#06x}  {ch.uuid}  {ch.properties}  ({ch.description})")
                for d in ch.descriptors:
                    print(f"    Desc  handle={d.handle:#06x}  {d.uuid}  ({d.description})")
                if target is None and uuid_kw in ch.uuid.lower():
                    target = ch
        print("===================================\n")

        if target is None:
            print(f"No characteristic UUID contains '{uuid_kw}'.")
            return
        print(f"Target characteristic: {target.uuid}  {target.properties}")

        # --- read / write 示範 ---
        if "read" in target.properties:
            try:
                val = await client.read_gatt_char(target)
                print(f"READ  {target.uuid}: {val.hex(' ')}")
            except Exception as e:
                print(f"READ  failed: {e}")
        if "write" in target.properties:
            try:
                await client.write_gatt_char(target, b"Hello from RPi", response=True)
                print("WRITE b'Hello from RPi' OK")
            except Exception as e:
                print(f"WRITE failed: {e}")

        # --- CCCD 設定 (作業重點) ---
        if "indicate" not in target.properties and "notify" not in target.properties:
            print("Target has neither notify nor indicate -> no CCCD.")
            return
        mode = "0x0002 (Indication)" if "notify" not in target.properties else "0x0001/0x0002"
        await client.start_notify(target, on_indication)
        print(f">>> CCCD of {target.uuid} written = {mode}  (subscribed)")

        print(f"\nListening for {LISTEN_SECONDS} s (send/indicate a value from the phone now) ...")
        try:
            await asyncio.sleep(LISTEN_SECONDS)
        finally:
            await client.stop_notify(target)
            print(">>> CCCD written = 0x0000 (unsubscribed)")

    print("Disconnected.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
