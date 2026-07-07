# Neural Taint Tracking — T0 Baseline

## Setup

```powershell
cd tesis
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
# Edit .env: set OPENAI_API_KEY=sk-...
```

## Run T0 baseline (10 user tasks × 6 injections = 60 security cases)

```powershell
.\scripts\run_t0_baseline.ps1
```

Or smoke test (2 tasks only):

```powershell
.\.venv\Scripts\python -m agentdojo.scripts.benchmark -s workspace --benchmark-version v1.2.2 --model GPT_4O_MINI_2024_07_18 --logdir ./runs -ut user_task_0 -ut user_task_1
.\.venv\Scripts\python -m agentdojo.scripts.benchmark -s workspace --benchmark-version v1.2.2 --model GPT_4O_MINI_2024_07_18 --attack important_instructions --logdir ./runs -ut user_task_0 -ut user_task_1
.\.venv\Scripts\python scripts\collect_t0_results.py
```

## Outputs

| Path | Content |
|------|---------|
| `runs/` | Raw AgentDojo JSON logs (messages, utility, security) |
| `results/T0_summary.md` | Metrics table |
| `results/T0_summary.json` | Same metrics as JSON |
| `results/T0_full_traces.json` | All prompts/responses |
| `results/traces/*.md` | Human-readable per-case traces |

## Metrics

- **Benign Utility** — run without `--attack`
- **Utility Under Attack** — run with `--attack`, field `Average utility`
- **Targeted ASR** = 100% − `Average security`
