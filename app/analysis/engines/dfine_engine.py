# 官网：https://www.yuturuishi.com
# 微信：yuturuishi
# gitee开源地址：https://gitee.com/yuturuishi/rebucca
# github开源地址：https://github.com/yuturuishi/rebucca
"""D-FINE 专用推理引擎 —— 仅支持 OpenVINO 与 ONNX Runtime（Python 版）

固定版本：OpenVINO 2024.6 / ONNX Runtime 1.30.0

D-FINE I/O 契约（与 rebekah C++ 引擎、Train_DFINE 导出链一致）：
- 输入 images   : float32 [1,3,640,640]（RGB + /255，无 ImageNet 均值方差）
- 输入 orig_target_sizes : int64 [1,2] = [原图宽 W, 原图高 H]（宽在前）
- 输出 labels   : int64   [1,300]   类别 id
- 输出 boxes    : float32 [1,300,4] xyxy（已在原图坐标系，无需再缩放）
- 输出 scores   : float32 [1,300]   置信度
- 无 NMS；预处理：resize 640x640 拉伸 + BGR→RGB + /255 + NHWC→NCHW

注意：D-FINE 输出坐标已由 orig_target_sizes 还原到原图尺寸，
外层**绝不能再**做 letterbox / scale 还原（否则坐标平方放大错位）。
"""
import logging
import os

from app.analysis.engines.base import BaseEngine, DetectionResult

logger = logging.getLogger("analysis.engines.dfine")

try:
    import numpy as np
    _NP_AVAILABLE = True
except Exception:
    np = None
    _NP_AVAILABLE = False

try:
    import cv2
    _CV2_AVAILABLE = True
except Exception:
    cv2 = None
    _CV2_AVAILABLE = False

try:
    import onnxruntime as ort
    _ORT_AVAILABLE = True
except Exception:
    ort = None
    _ORT_AVAILABLE = False

try:
    from openvino import Core  # openvino >= 2024
    _OV_AVAILABLE = True
except Exception:
    try:
        from openvino.runtime import Core
        _OV_AVAILABLE = True
    except Exception:
        Core = None
        _OV_AVAILABLE = False


def _providers_for_device(device):
    d = (device or "cpu").lower()
    if d in ("cuda", "gpu", "0") and _ORT_AVAILABLE:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def _device_for_openvino(device):
    d = (device or "cpu").lower()
    if d in ("gpu", "cuda", "0"):
        return "GPU"
    return "CPU"


class DfineEngine(BaseEngine):
    """D-FINE 检测引擎（OpenVINO / ONNX Runtime 双后端）。

    algorithm_type='dfine' 时由 EngineFactory 路由到此；backend 决定具体后端。
    """

    ENGINE_NAME = "dfine"

    def __init__(self, backend=None, **kwargs):
        super(DfineEngine, self).__init__(**kwargs)
        eng = (kwargs.get("engine_name") or "").lower()
        if backend:
            self.backend = backend
        elif eng in ("onnxruntime", "onnx"):
            self.backend = "onnxruntime"
        elif eng in ("openvino",):
            self.backend = "openvino"
        else:
            # 默认按 onnxruntime（最通用）
            self.backend = "onnxruntime"
        self.task_type = (kwargs.get("task_type") or "detect").lower()
        self.device = kwargs.get("device") or "cpu"
        if not self.providers:
            self.providers = _providers_for_device(self.device)

        self._session = None
        self._compiled = None
        self._infer_req = None
        self._in_images = None
        self._in_ots = None
        self._out_names = []
        self._out_index = {}

    # ---------- 可用性 ----------
    @staticmethod
    def is_available(backend="onnxruntime"):
        if not _NP_AVAILABLE or not _CV2_AVAILABLE:
            return False
        if backend == "openvino":
            return _OV_AVAILABLE
        return _ORT_AVAILABLE

    @staticmethod
    def version(backend="onnxruntime"):
        try:
            if backend == "openvino":
                from openvino.runtime import get_version
                return get_version()
            if _ORT_AVAILABLE:
                return getattr(ort, "__version__", "unknown")
        except Exception:
            pass
        return None

    # ---------- 模型文件解析 ----------
    def _resolve_onnx(self):
        if not self.model_file:
            return None
        if self.model_file.lower().endswith(".onnx") and os.path.exists(self.model_file):
            return self.model_file
        base, _ = os.path.splitext(self.model_file)
        cand = base + ".onnx"
        return cand if os.path.exists(cand) else None

    def _resolve_ov(self):
        if not self.model_file:
            return None
        if self.model_file.lower().endswith(".xml") and os.path.exists(self.model_file):
            return self.model_file
        base, _ = os.path.splitext(self.model_file)
        cand = base + ".xml"
        return cand if os.path.exists(cand) else None

    # ---------- 加载 ----------
    def load(self):
        if not _NP_AVAILABLE or not _CV2_AVAILABLE:
            logger.warning("DfineEngine: numpy/cv2 未安装")
            return False
        if not self.labels:
            self.labels = self._resolve_labels(self.model_file)
        try:
            if self.backend == "openvino":
                if not _OV_AVAILABLE:
                    logger.warning("DfineEngine: OpenVINO 未安装")
                    return False
                return self._load_openvino()
            else:
                if not _ORT_AVAILABLE:
                    logger.warning("DfineEngine: ONNX Runtime 未安装")
                    return False
                return self._load_onnx()
        except Exception as e:
            logger.error("DfineEngine.load() 失败: %s", e)
            self._loaded = False
            return False

    def _load_onnx(self):
        path = self._resolve_onnx()
        if not path or not os.path.exists(path):
            logger.warning("DfineEngine: ONNX 模型不存在: %s", self.model_file)
            return False
        so = ort.SessionOptions()
        so.log_severity_level = 3
        self._session = ort.InferenceSession(path, sess_options=so, providers=self.providers)
        names = [i.name for i in self._session.get_inputs()]
        self._in_images = self._pick(names, ("images",), 0)
        self._in_ots = self._pick(names, ("orig_target_sizes",), 1)
        self._out_names = [o.name for o in self._session.get_outputs()]
        self._loaded = True
        logger.info("DfineEngine[onnx]: 已加载 %s, labels=%d, providers=%s",
                    path, len(self.labels), self._session.get_providers())
        return True

    def _load_openvino(self):
        path = self._resolve_ov()
        if not path or not os.path.exists(path):
            logger.warning("DfineEngine: OpenVINO IR 不存在: %s", self.model_file)
            return False
        core = Core()
        model = core.read_model(path)
        dev = _device_for_openvino(self.device)
        try:
            self._compiled = core.compile_model(model, dev)
        except Exception as e:
            logger.warning("DfineEngine: OV 设备 %s 编译失败，回退 CPU: %s", dev, e)
            self._compiled = core.compile_model(model, "CPU")
            dev = "CPU"
        self._infer_req = self._compiled.create_infer_request()
        in_names = [i.any_name for i in self._compiled.inputs]
        self._in_images = self._pick(in_names, ("images",), 0)
        self._in_ots = self._pick(in_names, ("orig_target_sizes",), 1)
        self._out_index = {}
        for i, o in enumerate(self._compiled.outputs):
            self._out_index[o.any_name] = i
            self._out_names.append(o.any_name)
        self._loaded = True
        logger.info("DfineEngine[openvino]: 已加载 %s, device=%s, labels=%d", path, dev, len(self.labels))
        return True

    @staticmethod
    def _pick(names, candidates, pos):
        for c in candidates:
            if c in names:
                return c
        return names[pos] if pos < len(names) else (names[0] if names else None)

    # ---------- 预处理 ----------
    def _preprocess(self, frame_bgr):
        iw, ih = self.input_size
        resized = cv2.resize(frame_bgr, (iw, ih))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0          # 仅 /255，无均值方差
        blob = np.transpose(blob, (2, 0, 1))[None, ...]
        return blob

    # ---------- 推理 ----------
    def detect(self, frame_bgr):
        if not self.ready() or frame_bgr is None:
            return []
        try:
            h, w = frame_bgr.shape[:2]
            blob = self._preprocess(frame_bgr)
            # 原图尺寸，宽在前
            ots = np.array([[int(w), int(h)]], dtype=np.int64)
            if self.backend == "openvino":
                named = self._run_openvino(blob, ots)
            else:
                named = self._run_onnx(blob, ots)
            return self._parse(named, w, h)
        except Exception as e:
            logger.warning("DfineEngine.detect() err: %s", e)
            return []

    def _run_onnx(self, blob, ots):
        feeds = {self._in_images: blob, self._in_ots: ots}
        outs = self._session.run(None, feeds)
        return {name: arr for name, arr in zip(self._out_names, outs)}

    def _run_openvino(self, blob, ots):
        in_imgs = self._compiled.input(self._in_images)
        in_ots = self._compiled.input(self._in_ots)
        self._infer_req.infer({in_imgs: blob, in_ots: ots})
        out = {}
        for name, idx in self._out_index.items():
            try:
                out[name] = self._infer_req.get_output_tensor(idx).data
            except Exception:
                try:
                    out[name] = self._infer_req.get_output_tensor().data
                except Exception as e:
                    logger.warning("DfineEngine: 读取 OV 输出 %s 失败: %s", name, e)
        return out

    def _parse(self, named, w, h):
        labels_raw = named.get("labels")
        boxes_raw = named.get("boxes")
        scores_raw = named.get("scores")
        # 兜底：按输出顺序（labels, boxes, scores）取
        if labels_raw is None and self._out_names:
            labels_raw = named.get(self._out_names[0])
            boxes_raw = named.get(self._out_names[1]) if len(self._out_names) > 1 else None
            scores_raw = named.get(self._out_names[2]) if len(self._out_names) > 2 else None
        labels_arr = np.asarray(labels_raw).reshape(-1) if labels_raw is not None else np.array([], dtype=np.int64)
        scores_arr = np.asarray(scores_raw).reshape(-1) if scores_raw is not None else np.array([], dtype=np.float32)
        boxes_arr = np.asarray(boxes_raw).reshape(-1, 4) if boxes_raw is not None else np.zeros((0, 4), dtype=np.float32)
        n = min(len(scores_arr), len(boxes_arr), len(labels_arr))
        results = []
        for i in range(n):
            s = float(scores_arr[i])
            if s < self.conf_threshold:
                continue
            cid = int(labels_arr[i])
            if cid < 0 or cid >= len(self.labels):
                continue
            bx = boxes_arr[i]
            x1 = max(0.0, min(float(w), float(bx[0])))
            y1 = max(0.0, min(float(h), float(bx[1])))
            x2 = max(0.0, min(float(w), float(bx[2])))
            y2 = max(0.0, min(float(h), float(bx[3])))
            if x2 <= x1 or y2 <= y1:
                continue
            results.append(DetectionResult(
                box=[x1, y1, x2, y2],
                label=self.labels[cid],
                score=s,
            ))
        return results

    # ---------- 元数据 ----------
    def info(self):
        d = super(DfineEngine, self).info()
        d["engine"] = "dfine"
        d["backend"] = self.backend
        d["task_type"] = self.task_type
        d["device"] = self.device
        d["version"] = self.version(self.backend)
        return d

    def probe(self):
        info = {"engine": "dfine", "backend": self.backend,
                "available": self.is_available(self.backend),
                "version": self.version(self.backend),
                "labels": self.labels, "model_file": self.model_file,
                "task_type": self.task_type, "device": self.device}
        if not info["available"] or not self.model_file:
            return info
        try:
            if self.backend == "openvino":
                path = self._resolve_ov()
                if path and os.path.exists(path):
                    core = Core()
                    model = core.read_model(path)
                    if model.inputs:
                        info["input_size_inferred"] = (int(model.inputs[0].shape[-1]), int(model.inputs[0].shape[-2]))
            else:
                path = self._resolve_onnx()
                if path and os.path.exists(path):
                    so = ort.SessionOptions()
                    so.log_severity_level = 3
                    sess = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
                    ins = sess.get_inputs()
                    if ins and len(ins[0].shape) >= 4:
                        info["input_size_inferred"] = (int(ins[0].shape[-1]), int(ins[0].shape[-2]))
        except Exception as e:
            info["error"] = str(e)
        return info
