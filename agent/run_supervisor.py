"""Start the GPU fleet supervisor (run this on the RunPod pod at boot).

Example:
  cd agent && source .venv/bin/activate
  python run_supervisor.py
"""

from app.config import settings  # noqa: F401 — load agent/.env.local before supervisor imports

from app.fleet_supervisor import run_supervisor

if __name__ == "__main__":
    run_supervisor()
