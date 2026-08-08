"""Entrypoint for the SIP edge service (production telephony ingress).

  python run_sip_edge.py
"""

from app.sip_edge.server import run_sip_edge

if __name__ == "__main__":
    run_sip_edge()
