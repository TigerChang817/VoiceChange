# VoiceChange · AI 即時女聲變聲器

Windows 10 / 11 的桌面控制程式，用於 **麥克風 → 本機 RVC 串流轉換 → 虛擬麥克風 → Discord**。
使用 Python / Tk，AI 核心接 [w-okada/voice-changer](https://github.com/w-okada/voice-changer) 的 MMVCServerSIO 引擎；不是從零訓練的語音模型。

以即時聊天為設計目標：48kHz、64–256ms PCM 區塊、AI 引擎保留上下文及 SOLA 接縫處理、GPU 預熱、有限緩衝與過期音訊丟棄。**尚未在 Windows / NVIDIA / Discord 上完成端到端實測，不保證特定延遲或女聲自然度。** 不採用先錄一整段再做檔案轉換的流程。

## Windows 安裝

1. 安裝 [Python 3.11](https://www.python.org/downloads/)（含 Tcl/Tk 與 py launcher）。
2. 在專案目錄開啟 PowerShell，執行：

   ```powershell
   .\scripts\setup-windows.ps1
   ```

3. 從 [w-okada 官方發布頁](https://github.com/w-okada/voice-changer/blob/master/README_en.md) 取得對應 NVIDIA 的 **MMVCServerSIO / voice-changer Windows 版本**並完整解壓縮。此處接的是有 `/info`、`/update_settings`、`/test` 的 MMVC 協定，**不假定 VCClient v2 支援同一介面**。使用官方引擎版本與可信模型，不自動安裝顯示卡驅動。
4. 若已經用官方 Demo 載入模型，可以直接沿用。首次也可依官方說明啟動一次，準備女聲 **RVC `.pth` 或引擎支援的 ONNX 模型**，可附對應 `.index`。本專案未附模型；只載入可信來源且授權適用的模型，`.pth` 可能包含可執行的 pickle 內容。
5. 關閉之前手動啟動的 Demo／引擎以釋放 GPU。稍後在 VoiceChange 按「選擇 AI 引擎」，選取 **`start_http.bat` 呼叫的後端 `MMVCServerSIO.exe`**；不要選 `client` 資料夾裡的 Electron Demo（有些版本的兩個 exe 同名）。程式會先檢查啟動參數，再以背景 HTTPS 模式啟動後端，不開 Demo 視窗。首次下載模型可能需要數分鐘。首次配置完成後，下次開 VoiceChange 會自動啟動，無需再手動開 Demo。
6. 安裝 [VB-CABLE](https://vb-audio.com/Cable/)。若裝置已出現且能正常傳聲，可先使用；Discord 沒看到裝置時先完全退出再開啟。只有安裝程式明確要求或裝置無法正常載入時才重新啟動 Windows。
7. 啟動桌面程式：

   ```powershell
   .\scripts\start-windows.ps1
   ```

若 PowerShell 執行政策阻擋 `.ps1`，可直接執行對應命令，無須修改系統政策：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m voice_changer.app
```

## 單一介面啟動

- 「選擇 AI 引擎」：指定已解壓縮的後端 exe，成功啟動後記住路徑。「啟動 AI 引擎」可手動重試。
- VoiceChange 使用 **`https://127.0.0.1:18889`** 與它啟動的後端通訊；在使用者本機產生專用憑證並驗證 TLS，沒有關閉驗證或安裝系統根憑證。路徑、憑證、私鑰與引擎日誌存於 `%LOCALAPPDATA%\VoiceChange`，不要提交私鑰。
- 關閉 VoiceChange 時，只結束它自己啟動的引擎程序，不會關閉另外手動啟動的引擎。
- 「模型管理」會在瀏覽器開啟引擎官方頁面，僅在需要管理模型時使用。瀏覽器未信任本機專用憑證，可能顯示憑證提示；VoiceChange 自身使用專用憑證驗證，不受此提示影響。也可停止本程式，使用官方 Demo 管理模型後再回來。
- 相容舊流程：未設定整合引擎時，仍可連接手動啟動的 `http://127.0.0.1:18888`。
- **Windows 原始執行檔與 RTX 3060 Ti 的整合啟動仍待實機驗證。** 已驗證啟動參數、憑證、狀態切換及程序管理邏輯；不代表已在 Windows 執行引擎成功。

## Discord 設定

| 位置 | 裝置 |
| --- | --- |
| 本程式「麥克風輸入」 | 你的實體麥克風，優先試 WASAPI |
| 本程式「輸出裝置」 | **CABLE Input**，優先試 WASAPI |
| Discord「輸入裝置」 | **CABLE Output** |
| Discord「輸出裝置」 | 耳機 |

Windows 的麥克風與 CABLE 裝置都設為 48000Hz，允許桌面應用程式存取麥克風。先關閉 Discord 的 Krisp、降噪、自動增益，避免二次處理。不要將 CABLE Output / 立體聲混音選成本程式輸入，也不要把 Discord 聲音送回 CABLE，否則會回授。

「Discord 輸出裝置」選 CABLE Input，「監聽耳機」選你的耳機，兩者必須是不同裝置。選模型、音高先試 `+6` 半音、區塊先用 **128ms**，按「開始變聲」。按「監聽：關」即可聽到變聲後的自己，再按一次關閉監聽；開關不影響 Discord 收到的聲音。監聽預設關閉，戴耳機使用。若啟動時未選監聽耳機，請先停止再選裝置。

「Discord 音量」（0–200%）與「監聽音量」（0–100%，預設 50%）可在變聲中獨立調整；音量 0% 為靜音，放大時會限制峰值以避免數位溢位，但過度放大仍可能失真。音高、模型與裝置需停止後再調整。於 Discord 麥克風測試確認只有轉換後的聲音。停止、引擎失敗或逾時時不會自動直通原聲；Windows 的其他「聆聽此裝置」路由需自行關閉。

## 即時速度怎麼調

- 先看「推論往返」能否持續小於區塊長度。若 128ms 區塊的推論往返超過 128ms，無法持續跟上收音，會丟棄舊音訊，不能視為可用的即時聊天。
- RTX 3060 Ti 先用 128ms 起測；有餘裕時試 96ms、64ms；斷音就回到 128ms 或 192ms。區塊太小可能降低辨識與音色穩定度。
- 引擎內的 extra/context、crossfade、F0 與索引搜尋也會影響 GPU 負載與效果；先用官方預設，依該版本說明逐項調整。這些由引擎管理，本程式不額外疊加 250ms 上下文或重複接縫處理。
- 觀察「排隊」與丟棄數。程式最多保留一段待處理輸入、兩段輸出；過載會斷續，避免越講延遲越長。UI 的往返數值**不是完整端到端延遲**。
- 輸出 PortAudio 使用低延遲模式；優先 WASAPI。關閉其他 GPU 密集程式。顯示卡型號、模型與驅動都會影響速度，RTX 50 系列尤其要確認引擎的 PyTorch/CUDA 支援。
- 先把本機麥克風到 CABLE 的實測額外延遲控制在約 **150–250ms 內作為調校目標**；這是目標，尚無本機量測證據。Discord 與網路還會再增加延遲。若無法達成，應評估更輕量的模型或不同串流引擎。

測量時錄下同一個短促聲音的原始麥克風與 CABLE Output 兩條軌道，比較波形起點差；連續說話至少 5 分鐘，確認延遲沒有累積、沒有原聲漏出且丟棄數不持續增加。不要只憑 UI 推論時間宣稱延遲達標。

## 開發與驗證

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

測試涵蓋 PCM 格式／時間戳、模型與設定交握、錯誤回應、有限播放緩衝、停止與過載丟棄等邏輯。測試替身不會產生真實 AI 女聲，無法取代 Windows 音訊、GPU 模型與 Discord 的實測。音訊只傳到本機引擎（整合模式 `https://127.0.0.1:18889`，手動模式 `http://127.0.0.1:18888`），不落地錄音、不上傳遠端；引擎初次啟動與模型下載另需網路。

舊的 Java 猜數字程式已移除；這個專案現在以變聲器為主。
