"""Start the GPU fleet supervisor (24/7 on your GPU box)."""

from app.fleet_supervisor import run_supervisor

if __name__ == "__main__":
    run_supervisor()
