# Rebucca

**Language / 语言：** [简体中文](README.md) | [English](README_en.md)

**License:** MIT License, free for commercial use. See `LICENSE` for details.

- Website: https://www.yuturuishi.com
- WeChat: yuturuishi
- Gitee: https://gitee.com/yuturuishi/rebucca
- GitHub: https://github.com/yuturuishi/rebucca

- A multi-channel video access and intelligent surveillance/deployment analysis platform. Supports GB28181 / RTSP, YOLO small-model detection, OpenAI-compatible LLM review, polygon-based deployment zones, and structured alarms.

---

## Features

- Video access: RTSP / GB28181 streaming, ZLMediaKit forwarding, ONVIF discovery
- Intelligent analysis: **D-FINE real-time end-to-end detection (built-in, OpenVINO 2024.6 / ONNX Runtime 1.30.0 dual engines)** + YOLO-PyTorch / ONNX / OpenVINO small models + optional LLM review
- Deployment & alarms: polygon zones, 7 post-processing rules (intrusion / line-crossing / counting / direction / density / dwell / absence), every alarm backed by a snapshot, alarm rate strictly follows the detection frequency
- Operations: dashboard monitoring, streaming server start/stop, recording, one-click software restart, multi-language (7 languages)

---

## Requirements

- Python 3.10+
- FFmpeg (in PATH or configured in `config.json`)
- ZLMediaKit (streaming server, ports must match `config.json`)
- GPU optional
- D-FINE inference uses fixed versions: **OpenVINO 2024.6** and **ONNX Runtime 1.30.0** (see `requirements-windows.txt` / `requirements-linux.txt`)


```bash
On Linux, you need to manually enter zlm/bin.x86.gcc9.4 or zlm/bin.arm.gcc9.4 and make sure ./rebucca_zlm can be executed correctly.

If ./rebucca_zlm fails to run, refer to the following two ways to resolve the dependency issues.

(1) Solution 1
sudo chmod -R a+x *
echo "export LD_LIBRARY_PATH=\"$(pwd):\$LD_LIBRARY_PATH\"" >> ~/.bashrc && source ~/.bashrc

(2) Solution 2

sudo apt update
sudo apt install -y libsrtp2-1

// Download the Ubuntu 20 libssl1.1 package
wget http://security.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb
sudo dpkg -i libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb

// Fix dependencies
sudo apt -f install

```

**Install dependencies:**

```bash
# Windows
pip install -r requirements-windows.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
or
pip install -r requirements-windows.txt

# Linux
pip install -r requirements-linux.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
or
pip install -r requirements-linux.txt
```

---

## Quick Start

```bash
python manage.py runserver 0.0.0.0:10001
```

Open `http://<host>:10001/` in your browser. Default account: `admin`, default password: `admin888`.

For the first deployment, edit `config.json` (ports, ZLM, FFmpeg, etc.) and `settings.json` (UI branding). Most items take effect via hot reload after saving on the startup configuration page; changing the admin port or debug logging requires a service restart.

---

## Recommended Workflow

```
Video Management → Small Models → LLMs → Business Algorithms → Deployment Management → Start Analysis → Alarm Management
```

1. Add cameras and confirm streaming works
2. Upload/configure small models (flow 1/3) and LLMs (flow 2/3)
3. Create business algorithms, draw zones on the deployment page and bind algorithms
4. Click "Start Analysis" (**must be clicked again manually after a service restart**)
5. View results in Alarm Management

> Only hits on business algorithm rules produce alarms; merely detecting targets or detecting motion in the frame does not create alarm records.

---

## FAQ

| Issue | Solution |
|------|------|
| No alarms | Confirm streaming works, the zone has a bound algorithm, analysis is started, and detection classes match |
| Config changes not applied | Deployment/algorithm settings support hot reload; changing small models requires restarting analysis; changing ports requires a service restart |
| Port occupied | Kill leftover `python.exe` processes and restart |

Log directory: `log/`. For the version number, see `framework/settings.py`.

---

## Changelog

### v1.006
- 2026/10/12
- **New D-FINE real-time end-to-end object detection framework (core update of this release)**
  - rebucca now integrates the **D-FINE** detection framework as a built-in default general-purpose detection capability: out of the box, no model upload needed — D-FINE is available across the entire workflow (Small Models, Model Test, Business Algorithms, Deployment Management).
  - **D-FINE capabilities**: D-FINE is a real-time end-to-end detector proposed in ICLR 2025. With Fine-grained Distribution Refinement (FDR), it turns bounding-box regression into precise probability distribution prediction — **no NMS required, high localization accuracy, low inference latency**. At comparable speed it clearly outperforms YOLO-family models of similar size, making it ideal for video surveillance scenarios sensitive to both localization accuracy and real-time performance.
  - **Dual inference engines**: supports **OpenVINO (pinned 2024.6)** and **ONNX Runtime (pinned 1.30.0)** Python engines, running on both CPU and GPU. No dependency on Ultralytics — **completely avoids AGPL contamination**, making commercial deployment worry-free.
  - **Built-in default model**: the repository ships with the D-FINE-N (COCO 80 classes) model in both OpenVINO IR and ONNX formats (`static/upload/weight/dfine/`). It is auto-registered as the default general detection model on first launch, with **Chinese class names (80 classes)**; class names in alarm snapshots and the UI are fully localized in Chinese.
  - **Training framework**: D-FINE models are trained with our **ytstudio training framework** (`Train_DFINE`), which supports training N/S/M/X model tiers and fine-tuning on custom datasets. Artifacts can be exported with one click to static ONNX and OpenVINO IR (fp32) and deployed directly into rebucca. To train your own D-FINE model on your own data, export it and upload it on the Small Models page.
- **Alarm reliability: snapshot-alarm atomicity**
  - When alarm snapshot generation fails, the alarm is no longer written as a "snapshot-less" record — every alarm record now has a snapshot as its evidence, greatly improving alarm reliability.
- **Alarm rate strictly follows the detection frequency (important fix)**
  - Previously, multiple rules/targets in the same frame could stack up and produce excessive alarms. Now each video channel is throttled strictly by its deployment "detection frequency": at 1 frame/second, at most 1 alarm per second; multiple targets/rules in the same frame no longer stack. This eliminates alarm storms and saves storage and resources.
- **Performance optimizations**
  - Decode frequency is auto-aligned with the detection frequency (about 60% decoding overhead saved at 1s detection intervals); Chinese label drawing on alarm snapshots now uses ROI-local rendering (roughly an order of magnitude faster); snapshot JPEG quality optimized (80); zone polygon lookup switched to direct dictionary access.
- **Chinese text rendering support**
  - Added a Chinese drawing utility (PIL + Chinese font). Class labels and zone event badges (Alarm / Dwell) in alarm snapshots now render Chinese correctly instead of `???`.
- **UI improvement: one-screen dashboard**
  - The console dashboard is now compact: the "Streaming Service" and "Logs & Refresh" cards are merged into the two-column grid, and paddings/margins are tightened. The whole dashboard fits one screen on ordinary laptops (1366×768 and up) with no vertical scrolling.
- **Small Models page improvements**
  - The "Model Check Result" panel at the top is collapsed by default into a one-line summary (no more large banner when everything is fine); click to expand/collapse the details. It still auto-expands with a red warning when missing model files are detected.
  - A top entry to our open-source **ytstudio model training framework** (direct links to Gitee / GitHub) is now shown on the page, styled consistently and cleanly.
- **Favicon fixed and hardened on all pages**
  - Every browser tab now shows the site icon. `/favicon.ico` is served directly at the site root (no 302 redirect, with cache headers), completely bypassing browsers' stubborn favicon caching; also fixes the login page icon being overridden by an old logo link.
- **New "Restart Software" button**
  - The console home page now has a one-click restart entry. After confirmation, the service restarts automatically (with a watchdog process as a fallback to bring it back up) and all deployments stop cleanly.
- **Dependency versions pinned**
  - `requirements-*.txt` now pins `openvino==2024.6.0`, `onnxruntime==1.30.0`, and `pillow==10.4.0` (pillow 10.4.0 is compatible with Python 3.12).

### v1.005
- 2026/09/24
- **New "Absence Detection" post-processing rule (7th business rule)**
  - The inverse of the density rule: density alarms when "targets in zone ≥ threshold", absence alarms when "no target in zone for N consecutive seconds".
  - Choose "Absence Detection" on the business algorithm page and configure the absence threshold (seconds) on the control zone. When no matching target appears in the zone for the threshold duration, an alarm is raised; the rule automatically re-arms once a target returns.
  - Detection targets follow the algorithm's "target labels" configuration (e.g. person) — only matching targets count as "on duty".
  - Typical scenarios: equipment room attendance, cashier desk monitoring, duty post monitoring, construction site watch, workstation supervision.
  - Implementation: `POST_ABSENCE` and `ZoneModel.absence_threshold` in `models.py`; ABSENCE matching and alarm text in `biz_rules.py`; zone-level absence logic (presence timing / re-arm on return) in `pipeline.py`; `schema_upgrade.py` auto-adds the column for existing databases — no manual migration needed.
- **Added the missing density threshold input (important fix)**
  - Previously the density rule's `density_threshold` existed only as a backend field — the zone edit dialog had no input for it, so the threshold stayed 0 and density alarms could never fire.
  - The zone dialog now includes both "Density Threshold" and "Absence Threshold" inputs, saved with the zone on create/edit.
- **Alarm management supports density / absence type filters**
  - The alarm list adds "Density Alarm" and "Absence Alarm" filter options and type labels.
- **Zone-level alarm snapshot improvement**
  - Zone-level alarms (density / absence) have no specific target box; snapshots no longer draw a 0×0 detection box at the top-left corner, keeping only the zone polygon and the event badge.
- **Internationalization**
  - Added absence/density translation keys across all 7 languages; filled in the missing `zone_state_enabled` / `zone_state_disabled` keys for Simplified Chinese.

### v1.004
- 2026/09/02
- **Fixed incorrect detection box positions in deployment alarm snapshots (important)**
  - The shared inference pool pipeline (enabled by default) downscales frames to a long side of ≤1280 before sending to save transfer cost. The detection boxes / keypoints / segmentation polygons returned by inference are in the downscaled image coordinate system, but were previously drawn directly onto the original full-resolution snapshot without rescaling. As a result, detection boxes in alarm management images were shifted toward the top-left and too small — the higher the resolution, the worse the misalignment.
  - Detection result coordinates are now rescaled back to the original image coordinates (`remote_detector.py`), with zero-overhead passthrough when no downscaling occurs. This also fixes potential false/missed alarms caused by incorrect coordinates in zone-hit detection (point-in-polygon).
- **Fixed error when submitting the user edit form (`int() argument ... not 'NoneType'`)**
  - The database returns `is_active` as a boolean. The frontend assigned it directly to the status dropdown, causing the value match to fail; on submit it was serialized as `null`, and the backend's `int(None)` threw a raw exception.
  - Fixed on both ends: the frontend normalizes the status to `'1' / '0'` (`user/index.html`); the backend normalizes `is_active` with boolean/string compatibility and returns a business error message when `id` is missing (`UserView.py`).
- **Fixed the business algorithm edit dialog not showing previously selected detection targets**
  - When opening the edit dialog, previously selected detection targets were first populated correctly, but the subsequent `onSmallModelChange()` call re-rendered the select with an empty selection set, wiping out all restored selections — appearing as "no matter how many targets were selected, none show up when editing".
  - Now the select is re-rendered while preserving the current selection (consistent with `onDetectorModelChange` in the detect+ReID flow). When actually switching small models, old selections that are not in the new model's label list are still filtered out naturally (`algorithm/index.html`).

### v1.003
- 2026/08/06
- **Fixes related to LLM selection in business algorithms (important)**
  - LLM configuration now has a new "Name" field which can be left empty; on add/edit, if the name is empty, it falls back to the model name (`name = model_name`), preventing empty names in LLM configurations.
  - In business algorithm list/edit views, the display name of a bound LLM now falls back to the model name (`llm_name` falls back to `name or model_name`) instead of showing blank.
  - **Fixed an issue where, when editing a business algorithm bound to an LLM that has been disabled, the dropdown could not display the selection, looking like "configuration lost / not selectable"**: an echo item tagged with "[disabled]" is now added automatically, and each time the edit dialog opens, the previous echo item is cleaned up.
  - The label of the business algorithm "LLM" dropdown options is now `name || model_name || #id`, ensuring correct display when only the model name is filled in.
- **Added "Statistics Dashboard" (alarm situation overview)**
  - Alarm management now has a "Statistics Dashboard" page (`/alarm/dashboard`) for an at-a-glance view of the alarm situation.
  - 4 core stat cards: today's alarms, last-7-day alarms, total alarms, and number of involved cameras (all clickable to drill down to the corresponding list).
  - Alarm trend chart: supports switching between last 7 days / last 30 days.
  - Alarm type distribution and top cameras by alarm count.
  - Added the `alarm/openStats` API and a "Statistics Dashboard" entry in the left navigation.
- **i18n completion**
  - Completed the 16 translation keys related to the statistics dashboard in all 7 languages (es / ko / ru / vi / zh-hk / zh / en), fixing the issue where only zh / en had translations and other languages displayed raw keys.

> For the version number, see `PROJECT_VERSION` in `framework/settings.py`.

---

## Open Source License & Third-Party Dependencies

rebucca's **entire source code is open source under the MIT License** — free to use, modify, and distribute (including commercially).

At runtime this project aggregates several third-party components, each under its own license, which you must comply with:

| Component | Purpose | License |
|-----------|---------|---------|
| rebucca source code | The platform itself | MIT |
| ONNX Runtime | ONNX model inference | MIT |
| OpenVINO | OpenVINO model inference | Apache-2.0 |
| D-FINE framework | Real-time end-to-end detection (code & official weights) | Apache-2.0 |
| Ultralytics (YOLO-PyTorch engine) | Load `.pt` for YOLO inference | AGPL-3.0 |
| ZLMediaKit, etc. | Streaming media (`zlm/`) | MIT (see `zlm/THIRD_PARTY_LICENSES`) |
| PyTorch / OpenCV / Django, etc. | Base dependencies | BSD / Apache and other permissive licenses |

- **YOLO-PyTorch engine** depends on Ultralytics (AGPL-3.0): for commercial use (closed-source products, private deployments, SaaS, edge/embedded devices, etc.) you must comply with Ultralytics' license terms or purchase its Enterprise License; rebucca's MIT license does not cover that obligation. To avoid AGPL entirely, use the ONNX / OpenVINO engine instead.
- **Model weights**: the repository ships with example weights (`static/upload/weight/`); their license is the responsibility of the provider. Ultralytics pretrained weights (`*.pt`) are subject to AGPL / Enterprise license terms.
- **Version check (the only outbound request)**: when you open the "Version" page or the console dashboard, rebucca sends one version-check request to `http://www.yuturuishi.com/api/rebucca/checkVersion` to notify you of new versions. The request carries only the version number and OS/runtime environment info (hostname, system version, IP, uptime, etc.); it contains **no business data** such as video, accounts, or recordings. The previously periodic heartbeat reporting has been removed. If you prefer not to send this request, block it at the network level.
- **Disclaimer**: users are responsible for the legality of their deployment environment, models, and data. rebucca is provided "as is", without warranty.
