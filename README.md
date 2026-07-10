# Unix
```terminal
python -m venv .venv
bash ./.venv/bin/activate
python -m pip install -e .
evac-sim run config/scenario.yaml
evac-sim replay results/latest
evac-sim view-floorplan config/scw.json
```

# Windows
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

```powershell
evac-sim run config/scenario.yaml
evac-sim replay results/latest
evac-sim view-floorplan config/scw.json
```

Type [ctrl]+[c] to abort replay