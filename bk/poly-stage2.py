#!/usr/bin/env python3
import json, math
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import brier_score_loss

LOG_PREFIX = "[poly-stage2] "
EWMA_GRID = np.linspace(0.01, 0.50, 50)
BLEND_GRID = np.linspace(0.0, 1.0, 41)
N_BINS = 20


def log(msg):
    print(LOG_PREFIX + msg)

# ============================================================
# EVMA — с конца (правильный вариант)
# ============================================================
def evma_from_end(v, alpha):
    arr = np.array(v)
    if len(arr) == 0:
        return np.nan
    w = np.array([(1 - alpha)**i for i in range(len(arr))])[::-1]
    w = w / w.sum()
    return float(np.sum(arr * w))


# ============================================================
# Подбор лучшего alpha_evma
# ============================================================
def find_best_evma_alpha(windows, y_true):
    log("Подбор alpha_evma...")
    best_a = None
    best_brier = 999999

    for a in EWMA_GRID:
        preds = np.array([evma_from_end(w, a) for w in windows])
        b = brier_score_loss(y_true, preds)
        if b < best_brier:
            best_brier = b
            best_a = a

    log(f"Лучшая alpha_evma = {best_a:.4f}  (brier={best_brier:.5f})")
    return best_a


# ============================================================
# Подбор лучшего α бленда
# ============================================================
def find_best_blend(p_raw, p_evma, y_true):
    log("Подбор лучшего blend α...")
    best_a = None
    best_brier = 999999

    for a in BLEND_GRID:
        p = a*p_raw + (1-a)*p_evma
        b = brier_score_loss(y_true, p)
        if b < best_brier:
            best_brier = b
            best_a = a

    log(f"Лучший α_blend = {best_a:.4f}  (brier={best_brier:.5f})")
    return best_a


# ============================================================
# Калибровка — bins
# ============================================================
def compute_bins(preds, truths, n_bins=N_BINS):
    bins = [[] for _ in range(n_bins)]
    for p, y in zip(preds, truths):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, y))

    out = []
    for i, b in enumerate(bins):
        if len(b) == 0:
            out.append({"bin": i, "count": 0, "pred": None, "obs": None})
        else:
            arr_p = np.array([x[0] for x in b])
            arr_y = np.array([x[1] for x in b])
            out.append({
                "bin": i,
                "count": len(b),
                "pred": float(arr_p.mean()),
                "obs": float(arr_y.mean())
            })
    return out


# ============================================================
# Применение старых калибровочных коэффициентов
# ============================================================
def apply_old_correction(p, bins, k):
    idx = min(int(p * len(bins)), len(bins)-1)
    return float(max(0.0, min(1.0, p * k[idx])))


# ============================================================
# Основная функция STAGE2
# ============================================================
def main():
    raw_file = Path("backtest_results_stage2.json")
    if not raw_file.exists():
        log("ERROR: нет backtest_results_stage2.json")
        return

    data = json.loads(raw_file.read_text())

    # Эти списки формировались в первом стейдже
    p_raw = np.array([row["p_raw"] for row in data])
    y = np.array([row["y"] for row in data])
    windows = [row["window"] for row in data]

    # =======================================================
    # Подготовка калибровки из старого stage2.json
    # =======================================================
    corr_file = Path("stage2.json")
    if corr_file.exists():
        log("Загружаем предыдущую калибровку stage2.json...")
        corr = json.loads(corr_file.read_text())
        old_bins = corr["bins"]
        old_k = corr["k"]
    else:
        log("Старой калибровки нет — начальный запуск.")
        old_bins = None
        old_k = None

    # =======================================================
    # 1) Находим лучшую EVMA
    # =======================================================
    alpha_evma = find_best_evma_alpha(windows, y)
    p_evma = np.array([evma_from_end(w, alpha_evma) for w in windows])

    # =======================================================
    # 2) Находим лучший blend
    # =======================================================
    alpha_blend = find_best_blend(p_raw, p_evma, y)
    p_blended = alpha_blend*p_raw + (1-alpha_blend)*p_evma

    # =======================================================
    # 3) Применяем старую калибровку (если существует)
    # =======================================================
    if old_bins:
        log("Применяем старую калибровку...")
        preds = np.array([apply_old_correction(p, old_bins, old_k)
                          for p in p_blended])
    else:
        preds = p_blended

    # =======================================================
    # 4) Подсчёт скорингов
    # =======================================================
    b_raw = brier_score_loss(y, p_raw)
    b_evma = brier_score_loss(y, p_evma)
    b_blend = brier_score_loss(y, p_blended)
    b_final = brier_score_loss(y, preds)

    log(f"Brier raw      = {b_raw:.5f}")
    log(f"Brier evma     = {b_evma:.5f}")
    log(f"Brier blend    = {b_blend:.5f}")
    log(f"Brier final    = {b_final:.5f}")

    # =======================================================
    # 5) Формируем новую калибровку из финальных preds
    # =======================================================
    new_bins = compute_bins(preds, y)
    k = []
    for b in new_bins:
        if b["pred"] is None:
            k.append(1.0)
        else:
            if b["pred"] == 0:
                k.append(1.0)
            else:
                k.append(b["obs"] / b["pred"])

    # =======================================================
    # 6) Сохраняем stage2.json
    # =======================================================
    out = {
        "alpha_evma": alpha_evma,
        "alpha_blend": alpha_blend,
        "brier": {
            "raw": b_raw,
            "evma": b_evma,
            "blend": b_blend,
            "final": b_final
        },
        "bins": new_bins,
        "k": k
    }

    corr_file.write_text(json.dumps(out, indent=2))
    log("Готово. Калибровка записана в stage2.json")



if __name__ == "__main__":
    main()
