#!/usr/bin/env python3
"""
Auto-Retrain — scheduled ML model retraining with archiving + rollback.

Retrains the universal GBM model on fresh data, logs results,
and sends a Telegram notification with the new metrics.

Usage:
    python3 -m scripts.auto_retrain              # retrain + notify
    python3 -m scripts.auto_retrain --quiet      # retrain, no Telegram
    python3 -m scripts.auto_retrain --dry-run    # show what would happen
    python3 -m scripts.auto_retrain --force      # retrain now (skip schedule check)
    python3 -m scripts.auto_retrain --rollback   # restore previous model

Schedule: runs weekly (Sunday 6 AM ET) via launchd or cron.
"""
import argparse
import datetime
import glob
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("auto_retrain")

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
ARCHIVE_DIR = os.path.join(MODEL_DIR, "archive")

# TV-equivalent features added in the feature expansion
_TV_FEATURE_NAMES = {
    "rsi_14", "rsi_roc_3", "macd_hist_norm", "macd_hist_slope",
    "bb_pct_b", "bb_width", "stoch_k", "adx_14",
}


def get_current_metrics() -> dict:
    """Load current model metrics for comparison."""
    meta_file = os.path.join(MODEL_DIR, "meta_universal.json")
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def archive_models() -> str:
    """Archive current model files before retraining. Returns archive path."""
    if not getattr(settings, "ML_MODEL_ARCHIVE_ENABLED", True):
        return ""

    try:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        archive_path = os.path.join(ARCHIVE_DIR, date_str)
        os.makedirs(archive_path, exist_ok=True)

        model_files = [
            "gbm_reg_universal.joblib", "gbm_clf_universal.joblib",
            "scaler_universal.joblib", "meta_universal.json",
        ]
        archived = 0
        for fname in model_files:
            src = os.path.join(MODEL_DIR, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(archive_path, fname))
                archived += 1

        if archived == 0:
            return ""

        log.info("Archived %d model files to %s", archived, archive_path)

        # Prune old archives
        keep = getattr(settings, "ML_MODEL_ARCHIVE_KEEP", 4)
        archives = sorted(glob.glob(os.path.join(ARCHIVE_DIR, "????-??-??")))
        while len(archives) > keep:
            old = archives.pop(0)
            shutil.rmtree(old, ignore_errors=True)
            log.info("Pruned old archive: %s", os.path.basename(old))

        return archive_path

    except Exception as e:
        log.warning("Failed to archive models: %s", e)
        return ""


def rollback() -> bool:
    """Restore the most recent archived model."""
    try:
        archives = sorted(glob.glob(os.path.join(ARCHIVE_DIR, "????-??-??")))
        if not archives:
            log.error("No archives found to rollback to")
            return False

        latest = archives[-1]
        restored = 0
        for fname in os.listdir(latest):
            src = os.path.join(latest, fname)
            dst = os.path.join(MODEL_DIR, fname)
            shutil.copy2(src, dst)
            restored += 1

        log.info("Rolled back to archive %s (%d files)", os.path.basename(latest), restored)

        # Clear model cache
        from analysis.ml.predictor import _MODEL_CACHE, _META_CACHE
        _MODEL_CACHE.clear()
        _META_CACHE.clear()

        return True

    except Exception as e:
        log.error("Rollback failed: %s", e)
        return False


def retrain(lookback_days: int = None) -> dict:
    """Retrain the universal model and return results."""
    from analysis.ml.predictor import train_model, _MODEL_CACHE, _META_CACHE

    lookback = lookback_days or getattr(settings, "ML_RETRAIN_LOOKBACK_DAYS", 730)

    # Archive before retraining
    archive_path = archive_models()

    # Clear model cache so new models are loaded on next prediction
    _MODEL_CACHE.clear()
    _META_CACHE.clear()

    log.info("Retraining universal model (lookback=%d days)...", lookback)
    result = train_model("universal", lookback_days=lookback)

    if "error" in result:
        log.error("Training failed: %s", result["error"])
        if archive_path:
            result["archive_path"] = archive_path
    else:
        log.info("Training complete: hit_rate=%.1f%%, R2=%.4f, sharpe=%.3f",
                 result.get("hit_rate_test", 0),
                 result.get("r2_test", 0),
                 result.get("sharpe", 0))
        if archive_path:
            result["archive_path"] = archive_path

    return result


def notify_results(old_metrics: dict, result: dict) -> None:
    """Send training results to Telegram."""
    try:
        from signals.notifier import send_telegram

        if "error" in result:
            send_telegram(
                f"🔴 <b>ML Auto-Retrain Failed</b>\n"
                f"Error: {result['error'][:200]}"
            )
            return

        now = datetime.datetime.now().strftime("%b %d, %I:%M %p")
        new_hit = result.get("hit_rate_test", 0)
        old_hit = old_metrics.get("wf_hit_rate", 0)
        hit_delta = new_hit - old_hit
        dummy = result.get("dummy_baseline", 50)
        edge = new_hit - dummy

        new_r2 = result.get("r2_test", 0)
        old_r2 = old_metrics.get("wf_r2", 0)

        sharpe = result.get("sharpe", 0)
        n_samples = result.get("n_samples", 0)
        n_features = len(result.get("feature_importances", {}))
        old_n_features = old_metrics.get("n_features", 0)

        # Status emoji
        if edge > 3:
            status = "🟢"
            verdict = "Strong edge"
        elif edge > 0:
            status = "🟡"
            verdict = "Marginal edge"
        else:
            status = "🔴"
            verdict = "No edge — below baseline"

        # Warnings
        warnings = result.get("warnings", [])
        warn_lines = ""
        if warnings:
            warn_lines = "\n\n⚠️ <b>Warnings:</b>\n" + "\n".join(f"  • {w}" for w in warnings)

        # Top features
        importances = result.get("feature_importances", {})
        top_feats = list(importances.items())[:7]
        feat_lines = "\n".join(f"  {i+1}. {name} ({val:.3f})" for i, (name, val) in enumerate(top_feats))

        # TV feature delta — highlight which new TV features made it to top rankings
        tv_in_top = [(name, val) for name, val in importances.items() if name in _TV_FEATURE_NAMES]
        tv_top_10 = [name for name, _ in list(importances.items())[:10] if name in _TV_FEATURE_NAMES]
        tv_section = ""
        if tv_in_top:
            best_tv = tv_in_top[0]
            tv_section = (
                f"\n\n📊 <b>TV Features:</b>\n"
                f"  Best: {best_tv[0]} ({best_tv[1]:.3f})\n"
                f"  In top 10: {', '.join(tv_top_10) if tv_top_10 else 'none'}"
            )

        # Feature expansion note
        expansion = ""
        if old_n_features and n_features > old_n_features:
            expansion = f"\n  Features: {old_n_features} → {n_features} (+{n_features - old_n_features} TV indicators)"

        msg = (
            f"🤖 <b>ML Auto-Retrain Complete</b> — {now}\n"
            f"{'━' * 30}\n\n"
            f"{status} <b>{verdict}</b>\n\n"
            f"<b>Walk-Forward Results:</b>\n"
            f"  Hit Rate: {new_hit:.1f}% ({hit_delta:+.1f}pp vs last)\n"
            f"  Baseline: {dummy:.1f}% | Edge: {edge:+.1f}pp\n"
            f"  R²: {new_r2:.4f} (was {old_r2:.4f})\n"
            f"  Sharpe: {sharpe:.3f}\n"
            f"  Samples: {n_samples}"
            f"{expansion}\n\n"
            f"<b>Top Features:</b>\n{feat_lines}"
            f"{tv_section}"
            f"{warn_lines}"
        )

        send_telegram(msg)
        log.info("Sent retrain notification to Telegram")

    except Exception as e:
        log.warning("Failed to send notification: %s", e)


def log_retrain_history(result: dict) -> None:
    """Append retrain results to a history log for tracking improvement over time."""
    history_file = os.path.join(MODEL_DIR, "retrain_history.json")
    try:
        history = []
        if os.path.exists(history_file):
            with open(history_file) as f:
                history = json.load(f)

        entry = {
            "date": datetime.datetime.now().isoformat(),
            "hit_rate": result.get("hit_rate_test", 0),
            "r2": result.get("r2_test", 0),
            "sharpe": result.get("sharpe", 0),
            "dummy_baseline": result.get("dummy_baseline", 0),
            "n_samples": result.get("n_samples", 0),
            "n_features": len(result.get("feature_importances", {})),
            "warnings": len(result.get("warnings", [])),
        }
        history.append(entry)
        # Keep last 52 entries (1 year of weekly retrains)
        history = history[-52:]

        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)

    except Exception as e:
        log.warning("Failed to log retrain history: %s", e)


def run(notify: bool = True, lookback_days: int = None) -> dict:
    """Full retrain pipeline: save old metrics, retrain, compare, notify."""
    old_metrics = get_current_metrics()

    result = retrain(lookback_days=lookback_days)

    if "error" not in result:
        log_retrain_history(result)

    if notify:
        notify_results(old_metrics, result)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ML Auto-Retrain")
    parser.add_argument("--quiet", action="store_true", help="Skip Telegram notification")
    parser.add_argument("--dry-run", action="store_true", help="Show current metrics without retraining")
    parser.add_argument("--force", action="store_true", help="Force immediate retrain (skip schedule check)")
    parser.add_argument("--rollback", action="store_true", help="Restore previous model from archive")
    parser.add_argument("--lookback", type=int, default=None, help="Days of training data (default: from settings)")
    args = parser.parse_args()

    if args.rollback:
        success = rollback()
        if success:
            metrics = get_current_metrics()
            print("Rolled back. Current model metrics:")
            print(json.dumps(metrics, indent=2))
        else:
            sys.exit(1)
    elif args.dry_run:
        metrics = get_current_metrics()
        print("Current model metrics:")
        print(json.dumps(metrics, indent=2))
        meta_file = os.path.join(MODEL_DIR, "meta_universal.json")
        if os.path.exists(meta_file):
            mtime = os.path.getmtime(meta_file)
            age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(mtime)).days
            print(f"\nModel age: {age} days")
            print(f"Features: {metrics.get('n_features', '?')}")
            print(f"Retrain recommended: {'YES' if age >= 7 else 'No'}")
    else:
        result = run(notify=not args.quiet, lookback_days=args.lookback)
        if "error" in result:
            sys.exit(1)
