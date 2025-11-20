#### 1\. Localization (Sri Lankan Context)

WinUI 3 has excellent Unicode support, but rendering complex scripts (Sinhala/Tamil) requires specific font handling.

  * **Font:** Use **"Iskoola Pota"** or **"Nirmala UI"** as the fallback font family for Sinhala/Tamil to ensure characters render correctly (especially combined letters).
  * **Resource Management:**
      * `Strings/en-US/Resources.resw`
      * `Strings/si-LK/Resources.resw`
      * `Strings/ta-LK/Resources.resw`
  * **Currency:** Force formatting to LKR (Rs.) `CulturaInfo("si-LK")`.

#### 2\. Hardware Layer

  * **Scanner:** Implement `SerialPort` listening for older scanners and `HID` mode for modern USB scanners.
  * **Thermal Printer:** Do not use standard Windows Printing. Use **Raw RAW/ESC-POS commands** sent directly to the port (USB/Network). This is faster and "Industrial Grade."
      * *Library:* `ESCPOS_NET` or raw socket streams.
  * **Cash Drawer:** Triggered via the Printer (RJ11 signal sent via ESC/POS command).
