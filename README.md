# 🛡️ ARCreations — Google Flow Auto-Prompter

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-brightgreen.svg)]()
[![UI](https://img.shields.io/badge/UI-PySide6%20Glassmorphism-ff007f.svg)]()
[![Developer](https://img.shields.io/badge/Instagram-%40arcreations008-E1306C.svg)](https://www.instagram.com/arcreations008/?utm_source=chatgpt.com)

> **Premium Dark Glassmorphism Studio Edition** for batch-prompting and downloading creations on **Google Flow / ImageFX**. Designed for high-volume creators, artists, and studios requiring isolated multi-profile automation, human typing speeds, and safe cooldown routines.

---


- 👥 **Isolated Multi-Profile Architecture**:
  - Run up to **3 independent Chrome instances** simultaneously on dedicated remote debugging ports (`9222`, `9223`, `9224`).
  - Strict process window locks (`P1 🔒`, `P2 🔒`) prevent profile collisions and batch confusion.
  - Dedicated output subdirectories per profile (`Generated_Images/Profile_1`, etc.).

- ⚡ **Direct DOM Text Injection**:
  - Element-level text dispatch prevents typing interference or keyboard focus stealing when working across multiple windows.

- 🏷️ **Smart Prompt & Filename Parser**:
  - Generates clean, production-ready filenames formatted as `[number]-[duration].png` (e.g., `01-0.4.png`).

---

## 📥 Quick Download & Installation

### Option 1: Instant 1-Click Run (Recommended)
1. Download the latest **`ARCreations_FlowPrompter_v1.0.zip`** from the [Releases](releases) section.
2. Extract the folder anywhere on your Windows PC.
3. Double-click **`start.bat`**.
   - The launcher will automatically verify dependencies, install missing libraries, and launch the ARCreations Studio window.

### Option 2: Run From Source Code
```bash
# 1. Download this repository
git clone https://github.com/Aliairdrops/ARCreations-Flow-Prompter.git
cd ARCreations-Flow-Prompter

# 2. Install required Python packages
pip install -r requirements.txt

# 3. Install Playwright browser binaries
playwright install chromium

# 4. Launch the application
python app.py
```

---

## 🎯 How to Use

1. **Select Profile**: In the side panel, choose Profile 1, 2, or 3.
2. **Launch Chrome**: Click `▶ Launch (PX)` to open an isolated Chrome session. Log in once to your Google account on [flow.google.com](https://flow.google.com).
3. **Add Prompts**: Paste your prompt list into the left Prompts Workspace or click `📂 Load .txt File`.
4. **Configure Settings**: Set your output folder, optional character consistency tag (e.g. `@Character 1`), and cooldown timings.
5. **Start Automation**: Click `🚀 Start Batch Generation` and let ARCreations handle the prompt submission, waiting, and automatic image downloading.

---

## 💻 System Requirements

- **OS**: Windows 10 or Windows 11 (64-bit)
- **Python**: 3.10, 3.11, or 3.12 (Make sure *"Add Python to PATH"* is checked during installation)
- **Browser**: Google Chrome installed

---

## 👨‍💻 Developer & Support

Created & maintained by **ARCreations**.
-     Email: arazacreations@gmail.com
- 📸 **Instagram**: [@arcreations008](https://www.instagram.com/arcreations008/?utm_source=chatgpt.com)
- 💬 For custom features, private licenses, or inquiries, reach out directly via Instagram direct message.
