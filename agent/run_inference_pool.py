"""Entrypoint for the shared GPU inference pool (Phase 3).

  python run_inference_pool.py
"""

from app.inference_pool import run_inference_pool

if __name__ == "__main__":
    run_inference_pool()
