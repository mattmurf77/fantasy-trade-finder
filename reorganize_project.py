#!/usr/bin/env python3
"""Script to reorganize mixed Python project."""

import os
import shutil
from pathlib import Path

# Source and destination paths
SOURCE_DIR = Path("/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/project-reorganizer-workspace/test-projects/mixed-python-project")
DEST_DIR = Path("/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/project-reorganizer-workspace/iteration-1/mixed-python-project/without_skill/outputs/mixed-python-project")

# Create the destination directory structure
DEST_DIR.mkdir(parents=True, exist_ok=True)

# Define the new folder structure
FOLDERS = {
    "web_app": "FastAPI web service code",
    "ml_pipeline": "Data science and model training scripts",
    "docs": "Reference documentation and requirements",
    "models": "Trained model artifacts",
    "data": "Data files and experiment outputs",
}

# Create all subdirectories
for folder in FOLDERS.keys():
    (DEST_DIR / folder).mkdir(exist_ok=True)

# Map files to their new locations
FILE_MAPPING = {
    # Web app files (FastAPI and utilities used by API)
    "api.py": "web_app/api.py",
    "data_processor.py": "web_app/data_processor.py",
    "model.py": "web_app/model.py",
    "web/index.html": "web_app/index.html",
    "requirements.txt": "web_app/requirements.txt",

    # ML pipeline files (training and analysis)
    "train_model.py": "ml_pipeline/train_model.py",
    "analyze_results.py": "ml_pipeline/analyze_results.py",

    # Documentation
    "PRD.md": "docs/PRD.md",
    "EXPERIMENT_LOG.md": "docs/EXPERIMENT_LOG.md",

    # Model artifacts
    "trained_model.pkl": "models/trained_model.pkl",

    # Data files
    "results.csv": "data/results.csv",
}

# Copy files
for src_file, dest_file in FILE_MAPPING.items():
    src_path = SOURCE_DIR / src_file
    dest_path = DEST_DIR / dest_file

    if src_path.exists():
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)
        print(f"✓ Copied {src_file} → {dest_file}")
    else:
        print(f"✗ Source file not found: {src_file}")

# Create README files for each folder
README_CONTENT = {
    "web_app": """# Web Application (FastAPI)

This folder contains the FastAPI prediction service.

## Files
- **api.py**: Main FastAPI application with `/api/predict` and `/api/health` endpoints
- **model.py**: Model loading and inference logic
- **data_processor.py**: Input validation and data cleaning utilities
- **index.html**: Simple HTML frontend
- **requirements.txt**: Python dependencies

## Running the Server
```bash
pip install -r requirements.txt
uvicorn api:app --reload
```

## API Endpoints
- `POST /api/predict`: Make predictions with validated input
- `GET /api/health`: Check service health and model status

## Notes
- The model is loaded at startup from `../models/trained_model.pkl`
- Input validation ensures required fields (feature_1, feature_2, feature_3) are present
""",
    "ml_pipeline": """# ML Pipeline (Data Science)

This folder contains training and analysis scripts.

## Files
- **train_model.py**: Training script to build and save the model
- **analyze_results.py**: Analysis script for evaluating prediction accuracy

## Running Training
```bash
python train_model.py
```
This generates a trained model and saves it to `../models/trained_model.pkl`

## Running Analysis
```bash
python analyze_results.py
```
This analyzes results from `../data/results.csv` and generates performance metrics.

## Notes
- Training is offline and separate from the web service
- Results and predictions are logged to `../data/results.csv`
- See ../docs/EXPERIMENT_LOG.md for training history and performance notes
""",
    "docs": """# Documentation

Reference materials including product requirements and experiment notes.

## Files
- **PRD.md**: Product requirements document for the prediction API
- **EXPERIMENT_LOG.md**: Historical notes on model experiments and performance

## Key Info
- Current model: XGBoost with feature selection (91.2% accuracy, 12ms inference)
- API latency target: sub-100ms at p99
- Model hot-reload capability required
""",
    "models": """# Model Artifacts

Trained machine learning models.

## Files
- **trained_model.pkl**: Serialized trained model (XGBoost)

## Loading
Models are automatically loaded by the web app at startup. To use a new model:
1. Save it to this directory with appropriate naming
2. Update the MODEL_PATH in ../web_app/api.py
3. Restart the API service
""",
    "data": """# Data Files

Data files, predictions, and experiment outputs.

## Files
- **results.csv**: Prediction results and evaluation metrics

## Usage
- Generated during model training and analysis
- Used by analysis scripts to compute performance metrics
""",
}

for folder, content in README_CONTENT.items():
    readme_path = DEST_DIR / folder / "README.md"
    readme_path.write_text(content)
    print(f"✓ Created {folder}/README.md")

# Create a main README for the project
MAIN_README = """# Prediction API Project

A production ML service that exposes trained models via REST API. This project separates concerns into three logical components: the web application, ML pipeline, and documentation.

## Project Structure

```
.
├── web_app/              # FastAPI service & API logic
│   ├── api.py
│   ├── model.py
│   ├── data_processor.py
│   ├── index.html
│   ├── requirements.txt
│   └── README.md
├── ml_pipeline/          # Training & analysis scripts
│   ├── train_model.py
│   ├── analyze_results.py
│   └── README.md
├── models/               # Trained model artifacts
│   ├── trained_model.pkl
│   └── README.md
├── data/                 # Data files & outputs
│   ├── results.csv
│   └── README.md
├── docs/                 # Reference documentation
│   ├── PRD.md
│   ├── EXPERIMENT_LOG.md
│   └── README.md
└── README.md            # This file
```

## Getting Started

### Development

1. **Install web app dependencies:**
   ```bash
   cd web_app
   pip install -r requirements.txt
   ```

2. **Train a model (optional):**
   ```bash
   cd ../ml_pipeline
   python train_model.py
   ```

3. **Start the API server:**
   ```bash
   cd ../web_app
   uvicorn api:app --reload
   ```

4. **Access the API:**
   - Health check: http://localhost:8000/api/health
   - API docs: http://localhost:8000/docs

### Running Analysis

```bash
cd ml_pipeline
python analyze_results.py
```

## Architecture

**Web App** (`web_app/`) - Production service:
- FastAPI REST API with async endpoints
- Model loading and inference
- Input validation and error handling
- Static file serving

**ML Pipeline** (`ml_pipeline/`) - Development/offline:
- Training scripts (run offline)
- Analysis scripts (evaluate performance)
- Independent from production API

**Models** (`models/`) - Artifacts:
- Serialized trained models
- Loaded by API at startup

**Data** (`data/`) - Outputs:
- Prediction results
- Analysis metrics

**Docs** (`docs/`) - Reference:
- Product requirements (PRD.md)
- Experiment notes (EXPERIMENT_LOG.md)

## API Reference

### POST /api/predict
Predict using provided features.

**Request:**
```json
{
  "feature_1": "value",
  "feature_2": "value",
  "feature_3": "value"
}
```

**Response:**
```json
{
  "prediction": "result"
}
```

### GET /api/health
Check service health.

**Response:**
```json
{
  "status": "ok",
  "model_loaded": true
}
```

## Key Design Decisions

1. **Separation of Concerns**: Web app and ML pipeline are independent. Training happens offline; the API loads pre-trained models.
2. **Shared Utilities**: `data_processor.py` is used by both training and API to ensure consistent validation.
3. **Documentation**: All decisions documented in PRD and EXPERIMENT_LOG.
4. **Artifacts**: Models and data are separated from code for easier versioning and deployment.

## Performance Notes

- Current model (XGBoost): 91.2% accuracy, 12ms inference time
- API target: sub-100ms latency at p99
- Model hot-reload possible without downtime

## See Also

- `docs/PRD.md` for product requirements
- `docs/EXPERIMENT_LOG.md` for training history
- Each folder has its own README.md
"""

main_readme_path = DEST_DIR / "README.md"
main_readme_path.write_text(MAIN_README)
print(f"✓ Created main README.md")

print(f"\n✓ Project reorganized successfully!")
print(f"Output directory: {DEST_DIR}")
