# MLOps data pipelines — run from the repository root (PYTHONPATH = cwd).
# Requires: Python 3.11+, `pip install -r mlops_data/pipelines/requirements.txt` (see mlops-install).

.PHONY: mlops-install mlops-ingest mlops-synthetic mlops-dataset mlops-monitor mlops-promotion-gate \
	mlops-docker-pipelines mlops-docker-synthetic mlops-docker-monitor run-dashboard

PYTHON ?= python

mlops-install:
	$(PYTHON) -m pip install -r mlops_data/pipelines/requirements.txt

mlops-ingest:
	$(PYTHON) -m mlops_data.pipelines.cli_jigsaw

mlops-synthetic:
	$(PYTHON) -m mlops_data.pipelines.cli_synthetic

mlops-dataset:
	$(PYTHON) -m mlops_data.pipelines.cli_dataset_build --strict

mlops-monitor:
	$(PYTHON) -m mlops_data.pipelines.cli_monitoring --fail-on-breach

mlops-promotion-gate:
	$(PYTHON) -m mlops_data.pipelines.cli_promotion_gate

# Docker — requires .env from docker-compose-data.env.example (see mlops_data/pipelines/README.md)
mlops-docker-pipelines:
	docker compose -f docker-compose-data.yml --profile mlops build mlops-pipelines

mlops-docker-synthetic:
	docker compose -f docker-compose-data.yml --profile synthetic-dev run --rm mlops-synthetic

mlops-docker-monitor:
	docker compose -f docker-compose-data.yml --profile mlops run --rm mlops-pipelines \
		python -m mlops_data.pipelines.cli_monitoring --fail-on-breach

run-dashboard:
	streamlit run serving/monitoring/dashboard.py
