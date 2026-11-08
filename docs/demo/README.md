# Demo Snapshot — v1.0.0

This directory contains the frozen demo artifact for the public snapshot.

| File | Purpose |
|---|---|
| `preflight-review-packet.html` | Six-section review packet exported from run `R-DEMO-001` |
| `run-summary.json` | Machine-readable run snapshot (counts, metrics, audit head) |

The packet is generated from **synthetic fixtures only**. It contains no customer data and no
confidential Guidewire content. It is not an official Cloud Assurance result and not a deployable
Cloud artifact.

To reproduce locally:

```bash
make demo
# http://127.0.0.1:8000/packet?run=R-DEMO-001
```
