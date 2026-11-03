"""
core/badge.py — OpenCV / numpy 红点检测
"""
import math
from core.deps import HAS_CV2, HAS_NP, HAS_PIL, cv2, np


class BadgeCV:
    """
    HSV 色彩空间检测微信红色未读角标。
    优先 OpenCV（轮廓+圆形度过滤），降级时用纯 numpy 色彩扫描。
    """
    # 微信红点 HSV 范围（两段，覆盖红色绕回）
    HSV_L1 = (0,   140, 140);  HSV_H1 = (10,  255, 255)
    HSV_L2 = (168, 140, 140);  HSV_H2 = (180, 255, 255)

    MIN_AREA  = 22      # px²，太小的噪点排除
    MAX_AREA  = 300     # 真实角标不会超过这个大小
    MIN_CIRC  = 0.60    # 圆形度，带数字的角标略扁
    MERGE_THR = 22      # 合并距离（px），头像附近碎片合并为一个
        # ── X 轴过滤 ──────────────────────────────────────────
    CX_MIN = 52
    CX_MAX = 73

    # ── 主入口 ────────────────────────────────────────────
    @classmethod
    def detect(cls, pil_img) -> list[dict]:
        if HAS_CV2 and HAS_NP:
            badges = cls._detect_cv2(pil_img)
        elif HAS_NP:
            badges = cls._detect_numpy(pil_img)
        else:
            return []
        # 只保留 cx 在 52~73 之间的红点
        return [b for b in badges if cls.CX_MIN < b["cx"] < cls.CX_MAX]

    @classmethod
    def _detect_cv2(cls, pil_img) -> list[dict]:
        if pil_img is None:
            return []
        arr  = np.array(pil_img.convert("RGB"))
        bgr  = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        hsv  = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        m1   = cv2.inRange(hsv, cls.HSV_L1, cls.HSV_H1)
        m2   = cv2.inRange(hsv, cls.HSV_L2, cls.HSV_H2)
        mask = cv2.bitwise_or(m1, m2)
        k    = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k, iterations=1)

        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        badges = []
        for c in cnts:
            area = cv2.contourArea(c)
            if not (cls.MIN_AREA <= area <= cls.MAX_AREA):
                continue
            peri = cv2.arcLength(c, True)
            if peri == 0:
                continue
            circ = 4 * math.pi * area / (peri * peri)
            if circ < cls.MIN_CIRC:
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            r  = max(1, int(math.sqrt(area / math.pi)))

            # 只过滤边缘噪点（顶部/底部10px内忽略）
            img_h = arr.shape[0]
            if cy < 10 or cy > img_h - 10:
                continue

            # RGB 二次验证：真实红点 R 值必须明显高于 G 和 B
            # 防止皮肤色/暖色头像被 HSV 误检
            patch = arr[max(0,cy-5):cy+5, max(0,cx-5):cx+5]
            if patch.size > 0:
                avg = patch.mean(axis=(0,1))
                r_val, g_val, b_val = avg[0], avg[1], avg[2]
                # R 至少比 G 大 40，比 B 大 40，且 R > 150
                if not (r_val > 160 and g_val < 130 and r_val - g_val > 80 and r_val - b_val > 60):
                    continue

            badges.append({"cx": cx, "cy": cy, "area": area, "r": r})

        return _dedup(badges, cls.MERGE_THR)

    @classmethod
    def _detect_numpy(cls, pil_img) -> list[dict]:
        """OpenCV 不可用时的纯 numpy 降级方案"""
        if pil_img is None:
            return []
        a = np.array(pil_img.convert("RGB"))
        r, g, b = a[:,:,0].astype(int), a[:,:,1].astype(int), a[:,:,2].astype(int)
        mask = (r >= 180) & (g <= 85) & (b <= 85) & (r-g >= 110) & (r-b >= 110)
        if not mask.any():
            return []
        ys, xs = np.where(mask)
        if len(ys) < 15:
            return []

        # 简单行聚类
        pts = sorted(zip(ys.tolist(), xs.tolist()))
        clusters, grp = [], [pts[0]]
        for pt in pts[1:]:
            if abs(pt[0]-grp[-1][0]) < 20 and abs(pt[1]-grp[-1][1]) < 20:
                grp.append(pt)
            else:
                if len(grp) >= 15:
                    clusters.append(_centroid(grp))
                grp = [pt]
        if len(grp) >= 15:
            clusters.append(_centroid(grp))

        return _dedup(clusters, cls.MERGE_THR)

    # ── 调试 ─────────────────────────────────────────────
    @classmethod
    def draw_debug(cls, pil_img, out_path: str = "debug_badges.png"):
        """在图像上标注检测到的红点并保存"""
        if not HAS_CV2 or not HAS_NP or pil_img is None:
            return
        arr = np.array(pil_img.convert("RGB"))
        vis = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        for b in cls.detect(pil_img):
            cv2.circle(vis, (b["cx"], b["cy"]), b["r"]+5, (0, 255, 0), 2)
            cv2.putText(vis, f"r={b['r']}",
                        (b["cx"]-10, b["cy"]-b["r"]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
        cv2.imwrite(out_path, vis)


# ── 辅助函数 ──────────────────────────────────────────────
def _centroid(pts: list) -> dict:
    cy = int(sum(p[0] for p in pts) / len(pts))
    cx = int(sum(p[1] for p in pts) / len(pts))
    return {"cx": cx, "cy": cy, "area": len(pts), "r": 8}


def _dedup(badges: list, thr: float = 22) -> list:
    """合并距离小于 thr 的重叠检测结果"""
    if len(badges) <= 1:
        return badges
    used = [False] * len(badges)
    out  = []
    for i, a in enumerate(badges):
        if used[i]:
            continue
        grp = [a]
        for j, b in enumerate(badges):
            if i != j and not used[j]:
                if math.hypot(a["cx"]-b["cx"], a["cy"]-b["cy"]) < thr:
                    grp.append(b)
                    used[j] = True
        out.append({
            "cx":   int(sum(g["cx"]   for g in grp) / len(grp)),
            "cy":   int(sum(g["cy"]   for g in grp) / len(grp)),
            "area": grp[0]["area"],
            "r":    grp[0]["r"],
        })
        used[i] = True
    return out
