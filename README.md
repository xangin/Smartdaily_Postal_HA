# Smartdaily\_Postal\_HA

### 將今網智生活的包裹、寄放物、社區公告串接到 Home Assistant

> 本專案 fork 自 [andyching168/Smartdaily_Postal_HA](https://github.com/andyching168/Smartdaily_Postal_HA)，感謝原作者的 API 研究與整合基礎。

## ✨ 功能

- **包裹**：未領取／近期已取件清單、最新包裹、包裹照片
- **寄放物**：未領取／近期已領取清單、寄放物照片，自動判斷是否寄放給自己的戶號
- **社區公告**：未讀公告清單、最新公告（自動略過置頂的舊公告）、附件連結
- **社區點數**
- **事件通知**：新包裹、包裹領取、新寄放、寄放領取、新公告，**每一筆異動各觸發一次**
- **自動化藍圖**：勾選要通知的項目、填入通知動作即可使用
- **長期有效的連結**：照片自動轉成 JPEG（原圖為 WebP），公告附件點開時才取得
- 初次設定與齒輪選項都可選擇要啟用的類別與更新頻率

## 📦 安裝

### 前提條件

- Home Assistant 2025.1 以上
- 已安裝 HACS (Home Assistant Community Store)

### 取得 DeviceSn（裝置識別）

1. 在智生活 APP 首頁，點擊右上角的「條碼」（也就是領取包裹時給管理員掃描的頁面）
2. 將此頁面截圖
3. 到[條碼掃瞄網站](https://online-barcode-reader.inliteresearch.com/)，將截圖上傳辨識
4. 複製辨識出來的字串（也就是 `DeviceSn`（或 `DeviceCode`）的值）

> ⚠️ DeviceSn 等同長期登入憑證，擁有者可查閱你的姓名、電話、地址與包裹紀錄，請妥善保管。

### 透過 HACS 安裝

1. 在 HACS 右上角選單選擇「Custom repositories」，貼上 `https://github.com/xangin/Smartdaily_Postal_HA`，類型選擇「Integration」
2. 搜尋「智生活包裹追蹤」並安裝
3. 重新啟動 Home Assistant

### 設定

1. 「設定」→「裝置與服務」→「新增整合」，搜尋「智生活包裹追蹤」
2. 輸入 DeviceSn
3. 選擇社區
4. 選擇要啟用的類別（包裹、寄放物、社區公告、社區點數）與更新頻率
   - 包裹／寄放物：預設每 5 分鐘
   - 公告／點數：預設每 60 分鐘

之後可在整合頁面按「設定」（齒輪）隨時調整，關閉的類別會一併移除其實體。

## 🧩 實體

每個社區會建立一個「智生活 〈社區名稱〉」裝置，依啟用的類別建立以下實體：

| 類別 | 實體 | 狀態 | 主要屬性 |
|---|---|---|---|
| 包裹 | 最新包裹 | 未領取／已取件 | `p_name`、`postal_typeText`、`postal_logisticsText`、`postal_img`、`image_url`、`unclaimed_packages_count` |
| 包裹 | 未領取包裹 | 件數 | `items`：完整清單 |
| 包裹 | 近期已取件包裹 | 件數 | `items`：最近 10 筆 |
| 包裹 | 包裹照片（camera） | — | 最新未領取（沒有則為最新）的照片，JPEG |
| 包裹 | 包裹事件（event） | 觸發時間 | `arrived`／`picked_up` |
| 寄放物 | 未領取寄放物 | 件數 | `items`：完整清單 |
| 寄放物 | 近期已領取寄放物 | 件數 | `items`：最近 10 筆 |
| 寄放物 | 寄放物照片（camera） | — | 同上 |
| 寄放物 | 寄放物事件（event） | 觸發時間 | `deposited`／`collected` |
| 公告 | 未讀公告 | 則數 | `items`：未讀公告清單 |
| 公告 | 最新公告 | 標題 | `TypeName`、`created_at`、`link`、`recent`（最近 5 則） |
| 公告 | 公告事件（event） | 觸發時間 | `new` |
| 點數 | 社區點數 | 點數 | — |
| 共用 | API 連線異常（診斷） | on／off | 各更新群組的最後錯誤訊息 |

`items` 內每一筆都是 API 原始欄位，另外加上：

| 欄位 | 說明 |
|---|---|
| `arrived_at`／`picked_up_at` | 包裹到達／取件時間（ISO 格式，台灣時間） |
| `deposited_at`／`collected_at` | 寄放／領取時間 |
| `claimed` | 是否已領取 |
| `refrigerated` | 是否為冷藏包裹 |
| `is_mine` | 寄放物是否寄放給自己的戶號 |
| `image_url` | 長期有效的 JPEG 照片連結（優先使用 HA 外部網址，給通知用） |
| `image_path` | 同上的相對路徑（給儀表板用） |
| `link`／`link_path` | 公告連結（見下方說明） |

## 🔔 事件

每一筆異動都會發出一個 HA 事件，資料為該筆的完整欄位（同上表）加上 `type` 與 `entry_id`：

| 事件名稱 | `type` |
|---|---|
| `smartdaily_postal_ha_package` | `arrived` 新包裹、`picked_up` 已領取 |
| `smartdaily_postal_ha_collection` | `deposited` 新寄放、`collected` 已領取 |
| `smartdaily_postal_ha_announcement` | `new` 新公告 |

- 第一次載入只建立比對基準，不會發出事件
- 比對狀態會保存，HA 重啟期間的異動會在啟動完成後補發
- 同一次更新中有多筆異動（例如同時到兩件）會各發一次

## 🤖 自動化藍圖

[![匯入藍圖到 Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fxangin%2FSmartdaily_Postal_HA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsmartdaily_postal_ha%2Fsmartdaily_notify.yaml)

也可以到「設定」→「自動化與場景」→「藍圖」→「匯入藍圖」，貼上：

```
https://github.com/xangin/Smartdaily_Postal_HA/blob/main/blueprints/automation/smartdaily_postal_ha/smartdaily_notify.yaml
```

### 藍圖設定

| 設定 | 說明 |
|---|---|
| 通知項目 | 新包裹、包裹已領取、新寄放物、寄放物已領取、新公告（可複選） |
| 寄放物通知範圍 | 全部，或只有寄放給我們的 |
| 附上照片的項目 | 預設為新包裹、新寄放物 |
| 寄放物照片只在寄放給我們時附上 | 預設開啟 |
| 通知動作 | 你的通知方式，範例見下方 |
| 訊息內容（收合區塊） | 五種訊息的範本，可自訂 |

### 通知動作可使用的變數

| 變數 | 說明 |
|---|---|
| `{{ message }}` | 訊息文字 |
| `{{ image }}` | JPEG 照片連結；該項目未設定附照片時為空字串 |
| `{{ link }}` | 公告連結；非公告時為空字串 |
| `{{ kind }}` | 事件種類：`package_arrived`、`package_picked_up`、`collection_deposited`、`collection_collected`、`announcement_new` |
| `{{ data }}` | 事件原始資料，例如 `{{ data.p_name }}`、`{{ data.c_dtype }}`、`{{ data.is_mine }}` |
| `{{ recipient }}` | 寄放物收件人；收件人為「全戶通知」時改用戶號 |

訊息範本中同樣可以使用 `data` 與 `recipient`，例如預設的新寄放物訊息：

```jinja
{% if data.is_mine %}有新的寄放{{ data.c_dtype }}，記得領唷!!{% else %}寄放給{{ recipient }}的{{ data.c_dtype }}已登記{% endif %}
```

### 通知動作範例

在藍圖的「通知動作」選擇「新增動作」，或點右上角選單「以 YAML 編輯」貼上以下其中一種。

#### 1. 自訂通知腳本

如果你已經有自己的通知腳本（以下以接受 `message` 與 `img` 欄位的 `script.send_notify` 為例）：

```yaml
- action: script.send_notify
  data:
    message: "{{ message }}{{ '\n' ~ link if link else '' }}"
    img: "{{ image }}"
```

> 若腳本不接受空的 `img`，可改用條件判斷：
>
> ```yaml
> - if: "{{ image != '' }}"
>   then:
>     - action: script.send_notify
>       data:
>         message: "{{ message }}"
>         img: "{{ image }}"
>   else:
>     - action: script.send_notify
>       data:
>         message: "{{ message }}{{ '\n' ~ link if link else '' }}"
> ```

#### 2. 官方 notify（Home Assistant Companion App）

把 `mobile_app_your_phone` 換成你的裝置（可在「開發者工具」→「動作」搜尋 `notify.mobile_app` 找到）：

```yaml
- action: notify.mobile_app_your_phone
  data:
    title: 智生活
    message: "{{ message }}"
    data: >-
      {%- set ns = namespace(d={}) -%}
      {%- if image -%}{%- set ns.d = dict(ns.d, image=image) -%}{%- endif -%}
      {%- if link -%}{%- set ns.d = dict(ns.d, url=link, clickAction=link) -%}{%- endif -%}
      {{ ns.d }}
```

- 有照片時通知會顯示縮圖
- 新公告通知點下去會開啟公告（iOS 使用 `url`，Android 使用 `clickAction`）

#### 3. Telegram

需先設定 [Telegram bot](https://www.home-assistant.io/integrations/telegram_bot/) 整合。有照片時以圖片＋說明文字傳送，否則傳送文字：

```yaml
- if: "{{ image != '' }}"
  then:
    - action: telegram_bot.send_photo
      data:
        url: "{{ image }}"
        caption: "{{ message }}"
  else:
    - action: telegram_bot.send_message
      data:
        message: "{{ message }}{{ '\n' ~ link if link else '' }}"
```

> 有多個 bot 或聊天室時，請依 Telegram 整合文件加上 `config_entry_id` 或 `target`。

## 🔗 照片與公告連結

智生活的照片與附件網址都是 **15 分鐘就失效**的簽名網址，照片格式也是多數通知服務不支援的 WebP。本整合提供自己的連結：

- **照片連結**（`image_url`）：回傳轉好的 **JPEG**，有效 30 天
- **公告連結**（`link`）：點開時才向智生活取得附件，只有一個附件時直接開啟，多個附件時顯示附件清單頁面；有效 30 天

注意事項：

- ⚠️ 智生活的公告內容 API 會**將公告標為已讀**。本整合背景更新只讀取公告清單，**不會**改變已讀狀態，只有實際點開公告連結時才會標為已讀。
- 連結優先使用 HA 的**外部網址**（「設定」→「系統」→「網路」）。通知服務若需從外部抓圖（例如 LINE），HA 必須能從網際網路連線；未設定外部網址時連結為相對路徑，只能在 HA 介面內使用。
- 連結以簽名保護，**不需登入即可開啟**，只能存取該張照片或該則公告。請勿將連結公開分享。

## 📊 儀表板範例

未領取包裹（Markdown 卡片）：

```yaml
type: markdown
content: |
  {% for p in state_attr('sensor.zhi_sheng_huo_xxx_wei_ling_qu_bao_guo', 'items') or [] %}
  **{{ p.p_name }}**｜{{ p.postal_logisticsText }}｜{{ as_timestamp(p.arrived_at) | timestamp_custom('%m/%d %H:%M') }}{{ ' ❄️冷藏' if p.refrigerated else '' }}
  <img src="{{ p.image_path }}" width="120">
  {% else %}
  目前沒有未領取包裹
  {% endfor %}
```

未讀公告：

```yaml
type: markdown
content: |
  {% for a in state_attr('sensor.zhi_sheng_huo_xxx_wei_du_gong_gao', 'items') or [] %}
  - 【{{ a.TypeName }}】[{{ a.Title }}]({{ a.link_path }})（{{ as_timestamp(a.created_at) | timestamp_custom('%m/%d') }}）
  {% else %}
  沒有未讀公告
  {% endfor %}
```

> 實體 ID 依社區名稱產生，請到「設定」→「實體」搜尋「智生活」取得實際名稱。

## ⬆️ 從原版升級

- 「My Package Tracker」與原本的包裹照片 camera 沿用原實體 ID，屬性 `postal_img`、`postal_typeText`、`unclaimed_packages_count` 保留，既有自動化可繼續使用
- 舊版的「包裹 1~4」實體會自動移除，請改用「未領取包裹」的 `items` 屬性
- 舊設定沒有選項，升級後預設啟用全部類別，可到齒輪設定調整
- 修正：包裹時間原本會多加 8 小時（API 回傳的已是台灣時間）
- 修正：社區公告原本會顯示置頂的舊公告，現在改為最新的一般公告
- `collection/` 資料夾內的 command\_line 腳本功能已整合進本整合，可以移除相關的 `command_line` 設定

## 🔐 給今網的 APP 改善建議

針對目前條碼作為身分驗證憑證（DeviceSn）設計風險，以下為不需修改後端 API 的 UX 層改善提案：

- 條碼顯示前，**推薦使用者啟用 Face ID / 指紋驗證**
- App 預設**禁止螢幕截圖與錄影**（保留使用者手動開啟權限）
- 條碼畫面**加入警語提醒**（例如「此條碼具實際查詢權限，請勿隨意截圖或轉傳」）

上述機制能有效抑制條碼外洩的實務風險，**主要是因現有條碼具過大授權權限（可查詢個資與包裹紀錄）所致。**

## 📜 授權 License

本專案採用 [MIT License](LICENSE) 授權，詳情請見 LICENSE 檔案。

## ⚠️ 免責聲明 Disclaimer

本工具為非官方開發，僅供學術研究與個人自動化用途。  
使用本專案所造成之任何資料損失、帳號問題或法律糾紛，開發者不負任何責任。  
若官方對 API 做出限制或變更，本工具功能亦可能失效。

本專案無與今網智生活有任何關聯或合作。
