# ESLab HW3 — BLE Central (GATT Client) Programming

用 Raspberry Pi 上的 Python 程式當 **BLE Central**，連到手機上的 GATT Server，並把手機 App 的 **CCCD 設成 `0x0002`（開啟 Indication）**。

- 課程：電工實驗（嵌入式系統）EE3021

---

## 1. 架構

| | Raspberry Pi 4 | iPhone 15 Pro |
|---|---|---|
| BLE 角色 | **Central / GATT Client** | **Peripheral / GATT Server** |
| 軟體 | `ble_central_bleak.py`（Python + bleak + BlueZ） | LightBlue 虛擬裝置 Health Thermometer |
| 動作 | 掃描、連線、寫 CCCD = `0x0002` | 接受訂閱，之後可送出 Indication |

GATT 層級（目標是最下面的 CCCD）：

```
Service         0x1809  Health Thermometer
└─ Characteristic 0x2A1C  Temperature Measurement  [Indicate]
   └─ Descriptor  0x2902  Client Characteristic Configuration (CCCD)  ← 寫入 0x0002
```

CCCD 的值：

| 值 | 意義 |
|---|---|
| `0x0000` | 關閉 |
| `0x0001` | Notification（Server 推資料，Client 不用回覆） |
| `0x0002` | **Indication**（Server 推資料，Client 收到後要回 Confirmation） |

BLE 是 little-endian，所以 `0x0002` 在空中傳的 bytes 是 **`02 00`**。

## 2. 環境

| 項目 | 內容 |
|---|---|
| Central | Raspberry Pi 4 Model B 4GB（作業原本指定 Pi 3，Pi 4 同樣內建 BLE） |
| OS | Raspberry Pi OS 64-bit（Debian 13 trixie），kernel 6.18.50 |
| Bluetooth stack | BlueZ 5.82 |
| Python / 函式庫 | Python 3.13、[bleak](https://github.com/hbldh/bleak) |
| Peripheral | iPhone 15 Pro + **LightBlue** App（Virtual Device：Health Thermometer） |

> 作業說明中提到 iPhone 可以用類似的 App，因此用 LightBlue 取代 Android 的 BLE Tool。

## 3. 檔案

| 檔案 | 說明 |
|---|---|
| `ble_central_bleak.py` | 主程式（BLE Central） |
| `images/` | Demo 證據截圖 |

## 4. 程式流程

`ble_central_bleak.py`：

1. **掃描**：找名稱含關鍵字的裝置（例如 `Thermometer`）。iPhone 的 BLE 位址是會定期更換的隨機位址，所以用**名稱**找，不寫死 MAC。
2. **連線**，列出整個 GATT database（Service / Characteristic / Descriptor 與 handle）。
3. 依 **UUID** 找到目標 characteristic（`2a1c`）。handle 是 Server 動態分配的，iPhone 重開機後會改變，所以用 UUID 找比較可靠。
4. 呼叫 `start_notify()`：BlueZ 會寫入該 characteristic 的 CCCD。因為 2A1C 只有 `indicate` 屬性，寫入的值就是 **`0x0002`**。
5. 等待 60 秒，期間收到的 Indication 會印成 `[RX] ...`。
6. 呼叫 `stop_notify()` 把 CCCD 寫回 **`0x0000`**，然後斷線。

## 5. 執行方式

### 5.1 安裝

```bash
sudo apt update
sudo apt install -y python3-pip bluez
sudo pip3 install bleak --break-system-packages
sudo rfkill unblock bluetooth
bluetoothctl power on
```

### 5.2 手機

LightBlue → **Virtual** → `+` → 選 **Health Thermometer** → 開啟，並停在這個畫面（iOS 只有 App 在前景時才會廣播）。

### 5.3 第一次需要配對

iPhone 對部分 attribute 要求加密連線，第一次連線時會觸發配對（Numeric Comparison）。開另一個終端機，用 bluetoothctl 當 agent：

```bash
bluetoothctl
# 進入後輸入：
agent KeyboardDisplay
default-agent
```

接著執行主程式。出現 `Confirm passkey XXXXXX (yes/no)` 時輸入 `yes`，iPhone 上按「配對」。

### 5.4 執行

```bash
python3 ble_central_bleak.py Thermometer 2a1c
#                            ^ 裝置名稱關鍵字  ^ 目標 characteristic UUID
```

## 6. 結果與證據

### 6.1 Pi 端程式輸出

左：bluetoothctl 完成配對（`Confirm passkey ... yes`、`Bonded: yes`）。
右：連線 → GATT database → **`CCCD ... written = 0x0002 (Indication)`** → 60 秒後 **`written = 0x0000`** → 斷線。

![Pi output](images/pi_output.png)

### 6.2 手機端 Server log（LightBlue）

作業提到 App 介面可能看不到 CCCD 的值，可以用 server log 當證明。

| Did subscribe（CCCD → 0x0002） | Did unsubscribe（CCCD → 0x0000） |
|---|---|
| <img src="images/lightblue_subscribe.png" width="320"> | <img src="images/lightblue_unsubscribe.png" width="320"> |

- `Did subscribe to characteristic: UUID = 2A1C`，`SubscribedCentrals` 裡出現了 Pi。
- `Properties = 0x20` 就是 Indicate 屬性位元。
- 訂閱時間 **19:29:34**，取消訂閱 **19:30:34**，剛好差 60 秒，對應程式的等待時間。

### 6.3 空中封包（btmon）

在 Pi 上用 `sudo btmon > final.log` 錄下 HCI 封包，篩出寫入 CCCD（這次的 handle 是 `0x003c`）的部分：

```
2166  bluetoothd: < ACL Data TX ...                     25.853296
2167        ATT: Write Request (0x12) len 4
2168          Handle: 0x003c                            ← 2A1C 的 CCCD
2169            Data[2]: 0200                           ← 0x0002 = Indication
2181        ATT: Write Response (0x13) len 0            ← iPhone 確認寫入成功
...
4352  bluetoothd: < ACL Data TX ...                     86.001488
4353        ATT: Write Request (0x12) len 4
4354          Handle: 0x003c
4355            Data[2]: 0000                           ← 結束時寫回 0x0000
4357        ATT: Write Response (0x13) len 0
```

- `<` 代表 Pi 送出的封包。
- 兩次寫入相差約 60 秒，對應程式的等待時間。
- 同一份紀錄中有 `LE Connection Complete`，代表這次走的是 BLE。

![btmon CCCD proof](images/btmon_cccd_proof.png)

## 7. 遇到的問題與解法

| 問題 | 原因 | 解法 |
|---|---|---|
| `bluepy` 連 iPhone 一直 `Failed to connect` | bluepy 已多年未維護，在新版 BlueZ 上不穩定 | 改用 **bleak**（走 BlueZ D-Bus API） |
| 藍牙 `Powered: no`、`off-blocked` | 被 rfkill 擋住 | `sudo rfkill unblock bluetooth` |
| 寫 CCCD 回 `ATT Error 0x0E (Unlikely Error)` | iPhone 要求加密（`Insufficient Authentication`），需要配對，但 Pi 沒有 agent 回應 Numeric Comparison | 用 `bluetoothctl` 註冊 agent（`KeyboardDisplay`）並完成配對 |
| 配對後有時 GATT database 是空的 | iPhone 配對時一併產生傳統藍牙金鑰，之後用真實位址連線會走 BR/EDR（btmon 看到 `Connect Complete (0x03)` 而不是 `LE Connection Complete`） | 用名稱掃描，連到 iPhone 當下的隨機位址，走 BLE |
| 只在一邊刪除配對後，連線一直 `Connected: yes/no` 循環 | 兩邊的金鑰不一致，iPhone 拒絕連線 | Pi 和 iPhone 都清除配對（iPhone 重開機），再重新配對 |
| CCCD 的 handle 每次不一樣（`0x005c`、`0x003c`） | handle 由 Server 動態分配 | 程式用 **UUID** 找目標，不寫死 handle |
