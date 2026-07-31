# System Harness & Execution Directives for Forestry ROI Predictor

## 1. Context & Goal
- Contest: Forestry Statistics Data Utilization Contest (Data Analysis Section)
- Purpose: Predict farm-specific ROI/yield & determine optimal shipping timing using Forestry Microdata + KAMIS wholesale prices.
- Core Value: Overcome traditional Forest Service macro-averages by providing tailored ML recommendations for individual farms.

## 2. Token & Execution Constraints (Token Minimization & Speed)
- Keep responses concise. Minimal fluff, code-first.
- Do not repeat file contents unless requested.
- Run commands autonomously via CLI.

## 3. Hardware Acceleration Directives
- Environment: Dual NVIDIA RTX A6000 GPUs (48GB VRAM each), 48 vCPUs.
- Ensure XGBoost / PyTorch models utilize CUDA GPU acceleration (`tree_method='hist'`, `device='cuda'`).

## 4. Project Workflow & Harness Directives
### Phase 1: Context Ingestion & Preprocessing
1. Read documentation PDFs in `./docs/` and inspect CSV schemas in `./data/`.
2. Clean data: Handle missing values, filter outliers using IQR.
3. Feature engineering: Encode categorical variables, merge farm specs with KAMIS price trends.

### Phase 2: Modeling & Optuna Optimization
1. Model: XGBoost Regressor (CUDA acceleration enabled).
2. Hyperparameter Tuning: Implement `optuna` for automated tuning maximizing R² / minimizing RMSE.
3. Baseline Benchmarking: Evaluate & record metrics (R², RMSE, MAE) across:
   - Forest Service Baseline (Simple Group Average)
   - Linear Regression
   - Optuna-Tuned XGBoost

### Phase 3: Web Dashboard (Streamlit / FastHTML)
1. Build interactive web dashboard (`app.py`) for local/remote viewing.
2. Features: Farm input form, predicted ROI %, optimal shipment month recommendation, baseline comparison chart.

### Phase 4: Git Synchronization & Deliverable Summary
1. Auto-commit and push code to remote `origin/main` at key milestones.
2. Generate comprehensive contest analysis report in Markdown (`data_analysis_report.md`).

## 5. Immediate Initial Task
Upon initialization, check `./docs/` and `./data/`, create pipeline scripts, run data preprocessing, and launch Optuna tuning on CUDA GPU.
