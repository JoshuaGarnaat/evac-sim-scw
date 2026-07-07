# op unix
```terminal
python -m venv .venv
bash ./.venv/bin/activate
python -m pip install -e .
evac-sim run config/scenario_100_students.yaml
evac-sim replay results/latest
evac-sim analyze results/latest
```
type [ctrl]+[c] to abort replay

# op windows
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

```powershell
evac-sim run config/scenario_100_students.yaml
evac-sim replay results/latest
evac-sim analyze results/latest
```
