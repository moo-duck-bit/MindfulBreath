# MindfulBreath: Every Breath You Take, Every Mind You Wake

**MindfulBreath** is an interactive breathing system designed to support mindfulness novices by providing personalized biofeedback before meditation. It guides users through paced breathing using real-time respiratory data, visualized through dynamic animations of a human figure—mirroring the sequence of a traditional body scan.

This repository contains the system's codebase along with example content files and experimental assets used in our study.

---

## System Overview

![Mainfigure (1)](https://github.com/user-attachments/assets/43c80e2e-4f61-4ef5-8a9a-1b4fd7f276e9)

- The system consists of three stages:
  1. **Initialization** – calibrates the user’s breathing range.
  2. **Breath Cycle Recommendation** – suggests a personalized breathing pace (≈10% slower than baseline).
  3. **Breathing Exercise** – visualizes breath as flow through body regions in the order of:  
     `spine → right arm → left arm → head → right leg → left leg → heart`  
     Each part is animated per two breath cycles (inhale–exhale ×2), synchronized with a square pacing path.

---

## Experiment Setup

![FIGURE (4)](https://github.com/user-attachments/assets/f5fa562a-68af-4649-b59c-3ee19dbeed27)

The system was evaluated in a controlled study comparing passive relaxation, generic breathing apps, and MindfulBreath. Measures included EEG, respiration rate, and self-reported engagement.

---

## Per-Region Visualization Example

![image](https://github.com/user-attachments/assets/6d7eec2a-b7f3-45cb-b321-801067c09972)


Each inhale–exhale cycle activates a specific body part in the visualization. This sequence aligns with the body scan practice to scaffold user attention and embodied focus.

---

## Additional Content & Assets

Per-body-part image assets and supplementary visualizations can be found at the following link:  
👉 [Google Drive – MindfulBreath Visualization Content](https://drive.google.com/drive/folders/18w3h2rWj96sl3Ssxg8VQpKucEVUCWE38?usp=sharing)

---

## Contact
For questions or collaborations, please contact:
📧 ohchannah@skku.edu



---

## Try it online

**https://moo-duck-bit.github.io/MindfulBreath/** — runs entirely in the browser (`docs/`). Open it in desktop Chrome or Edge, then choose **Bluetooth** or **USB** to connect your own GDX-RB belt, or **try without a belt** (simulated breathing). The browser talks to the belt directly via Vernier's godirect-js (Web Bluetooth / WebHID), so no local server is needed. Session data can be downloaded as CSV on the final screen. If the page is embedded in another site, open it in a new tab so the sensor connection is allowed.

---

## Web UI + Go Direct Respiration Belt (GDX-RB, USB)

The original OpenCV interface (`main.py`) is ported to a browser UI that receives live force data from the belt through a local server.

```
GDX-RB (USB) ──godirect──▶ web/server.py ──SSE /stream──▶ http://localhost:8000 (web/static/index.html)
```

1. Turn the belt on, wear it around the chest, and connect it with the USB cable or leave Bluetooth on. Over Bluetooth, disconnect the sensor in Vernier Graphical Analysis first (only one app can stream from the belt at a time).
2. Run `run_web.bat` (or `python web/server.py`). Without a belt: `python web/server.py --demo`.
3. Open **http://localhost:8000** — the status pill turns green when the belt is streaming.

Flow (same as `main.py`): Initialization (20 s, min/max force) → Cycle detection (20 s) → Recommended pace (≈10% slower; `Enter` accept / `S` manual) → Breathing exercise (spine → right arm → left arm → head → right leg → left leg → heart, 2 breaths per region, square pacing path). `Esc` ends a session.

Each run saves `data/force_<time>_gdx.csv` (`Timestamp, Force Value`, as in `main.py`) and `data/events_<time>_gdx.csv` (stage changes, recommended/accepted pace, sections, participant ID) for usability evaluation.

Options: `--link auto|usb|ble` (default auto: USB first, then Bluetooth), `--port 8000`, `--sensor 1` (1: Force N), `--period 50` (sampling ms).
