*This defines the standard key map for CB POS. Consistency is key for training staff.*

#### 1\. The "Standard" Retail Key Map

We will stick to industry standards so experienced cashiers don't need retraining.

| Key | Action | Logic |
| :--- | :--- | :--- |
| **F1** | **Help / Shortcuts** | Shows an overlay of all available keys. |
| **F2** | **Product Search** | Opens a modal to search by name (for items without barcodes). |
| **F3** | **Change Qty** | Focuses the quantity field for the selected line item. |
| **F4** | **Void Line** | Removes the selected item from the cart. |
| **F5** | **Checkout / Pay** | Jumps straight to the Payment/Tender screen. |
| **F6** | **Hold Bill** | Suspends transaction (customer forgot wallet). |
| **F7** | **Recall Bill** | Recalls a suspended transaction. |
| **F8** | **Price Check** | Mode to scan item just to check price without adding to cart. |
| **F10** | **Manager Menu** | Returns/Refunds/End of Day (Requires Admin PIN). |
| **F12** | **Logout/Lock** | Security feature when cashier leaves counter. |
| **ESC** | **Cancel/Back** | Always closes the current modal or clears the current input. |
| **Enter** | **Add/Confirm** | Adds scanned item or confirms payment. |
| **Space**| **Quick Cash** | (On Pay Screen) Automatically inputs exact cash amount. |

#### 2\. WinUI 3 Implementation Strategy

The AI should use **KeyboardAccelerators** in the XAML for reliability, rather than `KeyDown` events which can be swallowed by focused elements.

**Example Requirement for AI:**

> "Implement `KeyboardAccelerators` at the Window level (MainWindow.xaml) so they work regardless of which button has focus. Create a `FocusService` that we can inject to force focus back to the Barcode Box."

-----

### UX Design: The "Hybrid" Button

Since you want it to be simple and touch-friendly, but keyboard-controlled, the UI components need to be "Hybrid".

**Instruction to AI for Button Styles:**
"Create a custom XAML Control Template for `ActionTiles`. It should look like a touch tile but render the Keyboard Shortcut in the top-right corner in a contrasting color."

**Visual Concept:**

```text
+-----------------------+
| [F5]            [IMG] |  <-- Hotkey visible
|                       |
|      PAYMENT          |  <-- Large Text (Sinhala/Tamil/Eng)
|                       |
+-----------------------+
```

-----

### Technical Challenge: The "Virtual Scanner"

Most barcode scanners act as a keyboard. They type `123456` and hit `Enter` very fast.

**Problem:** If the focus is on the "Quantity" box, and the cashier scans a barcode, the system will try to set the quantity to `885123...`.
**Solution (Add this to `technical_specs.md`):**

> **Scanner Discrimination:** We must distinguish between human typing and scanner input.
> *Logic:* If input speed is \> 50ms per character, it's a human. If \< 20ms, it's a scanner.
> *Implementation:* Use a global keyboard hook or a `RawInput` listener to detect the scanner device ID specifically, routing that input to the product search logic regardless of where the UI focus is.

