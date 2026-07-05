
`python -m venv .venv`
`.\.venv\Scripts\Activate.ps1`
`python -m pip install -e .`

`python -m evac_sim_scw --config config/scenario_100_students.yaml --mode batch`
`python -m evac_sim_scw --replay results/latest/replay.jsonl --mode replay`
`python -m evac_sim_scw --analyze results/latest`