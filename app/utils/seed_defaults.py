# 官网：https://www.yuturuishi.com
# 微信：yuturuishi
# gitee开源地址：https://gitee.com/yuturuishi/rebucca
# github开源地址：https://github.com/yuturuishi/rebucca
"""内置默认算法 seed —— 首次启动（Django ready）时幂等写入。

当前负责：
- D-FINE-n 通用检测（OpenVINO 2024.6 / ONNX Runtime 1.30.0 双引擎）
  权重文件位于 static/upload/weight/dfine/，由发布包内置，无需用户上传。
"""
import json
import logging
import os

logger = logging.getLogger("app.seed")

# COCO 80 类中文名称（与 D-FINE-n 官方 coco 权重一致，顺序=类别 id，不可变动）
COCO_80_CN = [
    "人", "自行车", "汽车", "摩托车", "飞机", "公交车", "火车", "卡车",
    "船", "红绿灯", "消防栓", "停车标志", "停车计费器", "长椅",
    "鸟", "猫", "狗", "马", "羊", "牛", "大象", "熊", "斑马",
    "长颈鹿", "背包", "雨伞", "手提包", "领带", "行李箱", "飞盘",
    "双板滑雪板", "单板滑雪板", "球类", "风筝", "棒球棒", "棒球手套", "滑板",
    "冲浪板", "网球拍", "瓶子", "酒杯", "杯子", "叉子", "刀",
    "勺子", "碗", "香蕉", "苹果", "三明治", "橙子", "西兰花", "胡萝卜",
    "热狗", "披萨", "甜甜圈", "蛋糕", "椅子", "沙发", "盆栽", "床",
    "餐桌", "马桶", "电视", "笔记本电脑", "鼠标", "遥控器", "键盘",
    "手机", "微波炉", "烤箱", "烤面包机", "水槽", "冰箱", "书",
    "时钟", "花瓶", "剪刀", "泰迪熊", "吹风机", "牙刷",
]

# 英文原名（仅用于识别存量英文记录并升级为中文，顺序同 COCO_80_CN）
COCO_80_EN = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork", "knife",
    "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed",
    "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]


def _weight_dir():
    base = None
    try:
        from django.conf import settings
        base = getattr(settings, "BASE_DIR", None)
    except Exception:
        pass
    if not base:
        try:
            from app.utils.GlobalUtils import g_config
            d = getattr(g_config, "uploadAlgorithmWeightDir", None)
            if d:
                return os.path.normpath(str(d))
        except Exception:
            pass
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.normpath(os.path.join(str(base), "static", "upload", "weight"))


def ensure_default_dfine_models():
    """幂等：若已存在 algorithm_type='dfine' 的小模型则跳过；否则写入 OV + ORT 两个内置条目。"""
    try:
        from app.models import AlgorithmModel
    except Exception as e:
        logger.warning("ensure_default_dfine_models: 无法导入模型: %s", e)
        return

    if AlgorithmModel.objects.filter(algorithm_type="dfine").exists():
        logger.info("ensure_default_dfine_models: D-FINE 默认模型已存在，跳过")
        return

    wd = _weight_dir()
    ov_file = "dfine/dfine_n_coco_ov2024.6_fp32_static.xml"
    ort_file = "dfine/dfine_n_coco_opset17_fp32_static.onnx"
    # 权重缺失则不写入，避免产生无法加载的脏数据
    if not (wd and os.path.isfile(os.path.join(wd, ov_file))):
        logger.warning("ensure_default_dfine_models: 缺少 OV 权重 %s，跳过 seed",
                       os.path.join(wd or "", ov_file))
        return
    if not (wd and os.path.isfile(os.path.join(wd, ort_file))):
        logger.warning("ensure_default_dfine_models: 缺少 ORT 权重 %s，跳过 seed",
                       os.path.join(wd or "", ort_file))
        return

    has_default = AlgorithmModel.objects.filter(is_default=1).exists()
    labels_json = json.dumps(COCO_80_CN, ensure_ascii=False)

    try:
        AlgorithmModel.objects.create(
            name="D-FINE-n (OpenVINO)",
            algorithm_type="dfine",
            task_type="detect",
            inference_engine="openvino",
            model_file=ov_file,
            model_file_size=os.path.getsize(os.path.join(wd, ov_file)),
            input_width=640,
            input_height=640,
            conf_threshold=0.4,
            iou_threshold=0.5,
            labels=labels_json,
            is_default=0 if has_default else 1,
            state=1,
        )
        AlgorithmModel.objects.create(
            name="D-FINE-n (ONNX Runtime)",
            algorithm_type="dfine",
            task_type="detect",
            inference_engine="onnxruntime",
            model_file=ort_file,
            model_file_size=os.path.getsize(os.path.join(wd, ort_file)),
            input_width=640,
            input_height=640,
            conf_threshold=0.4,
            iou_threshold=0.5,
            labels=labels_json,
            is_default=0,
            state=1,
        )
        logger.info("ensure_default_dfine_models: 已写入 D-FINE-n 默认模型（OpenVINO + ONNX Runtime）")
    except Exception as e:
        logger.exception("ensure_default_dfine_models: 写入失败: %s", e)


def upgrade_dfine_labels_to_chinese():
    """幂等升级：把存量 dfine 模型的 labels 统一重置为中文 80 类。

    背景：
    - 历史版本 seed 的是英文 COCO 80 类；
    - D-FINE 输出的 class id 固定 0~79，labels 必须恰好 80 条才能一一映射，
      不足 80（如被编辑过只剩 78 条）会导致对应类别检出被丢弃。
    故对 algorithm_type='dfine' 的记录：英文 COCO 或数量≠80，一律重置为中文 80 类。
    """
    try:
        from app.models import AlgorithmModel
    except Exception as e:
        logger.warning("upgrade_dfine_labels_to_chinese: 无法导入模型: %s", e)
        return
    try:
        en_set = set(COCO_80_EN)
        rows = AlgorithmModel.objects.filter(algorithm_type="dfine")
        updated = 0
        for m in rows:
            need_fix = False
            try:
                labels = json.loads(m.labels or "[]")
            except Exception:
                labels = []
            if not isinstance(labels, list) or len(labels) != len(COCO_80_CN):
                need_fix = True
            elif set(str(x) for x in labels) & en_set:  # 含任一英文原名即视为旧数据
                need_fix = True
            if need_fix:
                m.labels = json.dumps(COCO_80_CN, ensure_ascii=False)
                m.save(update_fields=["labels", "last_update_time"])
                updated += 1
                logger.info("upgrade_dfine_labels_to_chinese: 已更新模型 id=%s name=%s 的类别为中文 80 类",
                            getattr(m, "id", "?"), m.name)
        if updated:
            logger.info("upgrade_dfine_labels_to_chinese: 共更新 %d 条 dfine 模型类别", updated)
    except Exception as e:
        logger.exception("upgrade_dfine_labels_to_chinese: 升级失败: %s", e)


def upgrade_dfine_biz_target_labels():
    """幂等升级：绑定 D-FINE 模型的业务算法，target_labels 英文→中文。

    背景（2026-10-11 线上事故）：模型 labels 升级为中文 80 类后，存量业务
    算法的 target_labels 仍是英文（如 person/bus），规则按标签匹配永远
    不命中 → 布控在跑但一条报警都不产生。
    处理：仅处理 small_model.algorithm_type == 'dfine' 的业务算法
    （YOLO 等其他模型的规则不受影响），把 target_labels 里的英文 COCO
    类名逐项映射为对应中文，非 COCO 项原样保留；已是中文则跳过（幂等）。
    """
    try:
        from app.models import BizAlgorithmModel
    except Exception as e:
        logger.warning("upgrade_dfine_biz_target_labels: 无法导入模型: %s", e)
        return
    en2cn = dict(zip(COCO_80_EN, COCO_80_CN))
    try:
        rows = BizAlgorithmModel.objects.select_related("small_model").all()
        updated = 0
        for b in rows:
            sm = getattr(b, "small_model", None)
            if sm is None or getattr(sm, "algorithm_type", "") != "dfine":
                continue
            try:
                targets = json.loads(b.target_labels or "[]")
            except Exception:
                continue
            if not isinstance(targets, list):
                continue
            en_set = set(COCO_80_EN)
            if not any(str(t) in en_set for t in targets):
                continue  # 无英文 COCO 项，视为已升级
            new_targets = [en2cn.get(str(t), str(t)) for t in targets]
            # 去重保序（英文映射可能把不同写法合并，正常情况一一对应）
            seen = set()
            new_targets = [t for t in new_targets if not (t in seen or seen.add(t))]
            b.target_labels = json.dumps(new_targets, ensure_ascii=False)
            b.save(update_fields=["target_labels", "last_update_time"])
            updated += 1
            logger.info("upgrade_dfine_biz_target_labels: 已更新业务算法 id=%s name=%s 的检测目标为中文",
                        getattr(b, "id", "?"), b.name)
        if updated:
            logger.info("upgrade_dfine_biz_target_labels: 共更新 %d 条业务算法检测目标", updated)
    except Exception as e:
        logger.exception("upgrade_dfine_biz_target_labels: 升级失败: %s", e)
