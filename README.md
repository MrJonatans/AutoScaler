# AutoScaler

ML-based predictive autoscaling system for Kubernetes.  
Использует LSTM нейросеть для прогноза CPU и упреждающего масштабирования через HPA.

## Архитектура

```
┌──────────────┐    /metrics     ┌──────────────┐
│  FastAPI App │ ───────────────▶│  Prometheus   │
│  (в k8s)     │                 │  (в k8s)      │
│  порт 8000   │◀────────────────│  порт 9090    │
└──────────────┘  scrape 15s     └──────┬───────┘
                                        │
                              ┌─────────▼────────┐
                              │  Predictor        │
                              │  (на хосте)       │
                              │  порт 8001        │
                              │  ┌──────────────┐ │
                              │  │ LSTM модель   │ │
                              │  └──────────────┘ │
                              └─────────┬────────┘
                                        │ predicted_cpu
                              ┌─────────▼────────┐
                              │ Prometheus-Adapter│
                              │ ext.metrics.k8s.io│
                              └─────────┬────────┘
                                        │
                              ┌─────────▼────────┐
                              │  HPA              │
                              │  (predicted_cpu)  │
                              └──────────────────┘
```

**Гибридный режим (рекомендуемый):**
- Приложение и инфраструктура (Prometheus, Grafana, HPA) — в Kubernetes
- Predictor (ML inference) запускается локально на хосте — так не нужно тащить torch в кластер
- Prometheus scrapet внешний predictor как `external-predictor` target
- Predictor забирает исторические метрики из Prometheus, прогоняет через LSTM, выставляет `predicted_cpu`

## Структура проекта

```
AutoScaler/
├── src/
│   ├── app/                   # FastAPI-приложение (симулятор нагрузки)
│   │   ├── main.py            # Точка входа FastAPI, endpoint /load, /metrics, /health
│   │   └── metrics.py         # Prometheus-метрики (cpu_usage_percent, requests_total)
│   ├── ml/                    # Машинное обучение
│   │   ├── model.py           # LSTM (input=5 признаков, hidden=64, layers=2, output=1)
│   │   ├── train.py           # Обучение: создание последовательностей, train/test split
│   │   ├── predict.py         # Однократный прогноз (legacy)
│   │   └── utils.py           # create_sequences, create_time_features, preprocessing
│   └── scaler/                # Сервис предсказателя
│       ├── config.py          # Настройки через env: PROMETHEUS_URL, SEQUENCE_LENGTH и т.д.
│       ├── predictor.py       # PredictorService — сбор метрик, прогноз, экспорт метрики
│       └── test_predictor.py  # Unit-тесты предсказателя
├── helm/
│   └── autoscaler/            # Helm chart для развёртывания
│       ├── Chart.yaml         # v0.1.0, appVersion 1.0.0
│       ├── values.yaml        # Все настройки: образы, ресурсы, HPA, адаптеры
│       └── templates/
│           ├── _helpers.tpl       # Общие шаблоны (labels, namespace)
│           ├── namespace.yaml     # autoscaling-ns
│           ├── app-deployment.yaml
│           ├── app-service.yaml   # NodePort :30080
│           ├── predictor-deployment.yaml  # (отключён по умолчанию, enabled: false)
│           ├── hpa.yaml           # predicted_cpu + cpu_usage_percent (external metrics)
│           ├── prometheus/
│           │   ├── configmap.yaml
│           │   ├── deployment.yaml
│           │   └── service.yaml   # NodePort :30909
│           ├── prometheus-adapter/
│           │   ├── configmap.yaml # external rules: predicted_cpu, cpu_usage_percent
│           │   ├── deployment.yaml
│           │   ├── rbac.yaml
│           │   ├── service.yaml
│           │   └── serviceaccount.yaml
│           ├── kube-state-metrics/
│           │   ├── clusterrole.yaml
│           │   ├── clusterrolebinding.yaml
│           │   ├── deployment.yaml
│           │   ├── service.yaml
│           │   └── serviceaccount.yaml
│           ├── node-exporter/
│           │   ├── daemonset.yaml
│           │   └── service.yaml
│           └── grafana/
│               ├── configmap-datasource.yaml        # Prometheus datasource provisioning
│               ├── configmap-dashboard.yaml         # AutoScaler dashboard JSON
│               ├── configmap-dashboards-provider.yaml
│               ├── deployment.yaml
│               └── service.yaml                     # NodePort :30300
├── scripts/
│   ├── deploy.sh              # Полный цикл: сборка образов → transfer → helm upgrade
│   ├── generate_data.py       # Генерация синтетических данных (14 дней, 1 мин)
│   ├── prepare_azure_data.py  # Конвертация Azure trace → data.csv (30 дней, 1 мин)
│   ├── collect_live_data.py   # Сбор real-time CPU из Prometheus в CSV
│   └── visualize_data.py      # Визуализация data.csv
├── tests/
│   ├── unit/
│   │   ├── test_model.py      # Тесты LSTM, create_sequences, preprocessing
│   │   └── test_predictor.py  # (через src/scaler/test_predictor.py)
│   └── integration/
│       ├── load_test.py       # Нагрузочный тест с ramp-up / burst (асинхронный)
│       └── load_test_csv.py   # CSV-driven нагрузка — воспроизводит data.csv в real-time
├── requirements.txt           # Все зависимости (включая torch)
├── requirements-app.txt       # Лёгкие зависимости для app (без torch)
├── requirements-predictor.txt # Зависимости для predictor (с torch)
├── Dockerfile                 # Multi-stage образ для app (без torch)
├── Dockerfile.predictor       # Multi-stage образ для predictor (с torch)
├── model.pth                  # Обученная LSTM модель
├── scaler.pkl                 # MinMaxScaler (5 признаков: CPU + 4 time features)
├── model_scaled.pth           # Переобученная модель (на data_scaled.csv)
├── scaler_scaled.pkl          # Scaler для data_scaled
├── data.csv                   # Обучающий датасет (30 дней CPU, 1 мин)
├── data_scaled.csv            # Масштабированный датасет (нормализованный)
├── live_data.csv              # Собранные в реальном времени метрики
├── data-visual.csv            # Визуализационный датасет
├── azure_trace.csv            # Сырой Azure trace (VM cpu_usage, assigned_mem)
├── Chart.yaml                 # Корневой Chart.yaml (deprecated)
├── model_evaluation.png       # График оценки модели (после обучения)
├── model_evaluation_full_15min.png  # Оценка модели на 15-мин горизонте
├── data_visualization.png     # Визуализация данных
└── .gitignore
```

## Компоненты

### FastAPI App (`src/app/main.py`)
- `GET /load?n=1000` — симуляция CPU-нагрузки (факториал 500, sub-linear scaling)
- `GET /metrics` — Prometheus endpoint с `cpu_usage_percent` и `requests_total`
- `GET /health` — healthcheck
- CPU измеряется process-level через `psutil` в фоновом потоке

### ML Model (`src/ml/model.py`)
- **Архитектура**: LSTM (input=5 → hidden=64 → 2 слоя → Linear → 1)
- **Признаки на входе**:
  1. CPU usage (нормализованный)
  2. `hour_sin` — циклический час дня
  3. `hour_cos` — циклический час дня
  4. `day_sin` — циклический день недели
  5. `day_cos` — циклический день недели
- **Sequence length**: 60 минут (по умолчанию)
- **Prediction horizon**: 1 минута вперёд (настраивается)
- **Loss**: MSELoss, **Optimizer**: Adam (lr=0.001), **Epochs**: 30

### Predictor Service (`src/scaler/predictor.py`)
- Циклически (каждые INTERVAL=60с) опрашивает Prometheus (`avg_over_time(cpu_usage_percent[1m])`)
- Формирует 5-признаковый input и прогоняет через LSTM
- Экспортирует метрику `predicted_cpu` на порту 8001
- Сравнивает прогноз с порогами (scale_up/scale_down)

### HPA (`helm/autoscaler/templates/hpa.yaml`)
- Использует **external** метрики (через prometheus-adapter)
- Основная метрика: `predicted_cpu > 30` (целевое значение)
- Дополнительная метрика (включается `useCurrentCpu=true`): `cpu_usage_percent > 40%`

### Prometheus Adapter
- Проксирует `predicted_cpu` и `cpu_usage_percent` из Prometheus в `external.metrics.k8s.io`
- External rules: `avg(predicted_cpu)`, `avg(cpu_usage_percent)`

### Grafana Dashboard
- **CPU Usage vs Predicted** (timeseries) — сравнение `cpu_usage_percent` и `predicted_cpu`, пороги 70%/90%
- **Request Rate (RPS)** (timeseries) — `rate(requests_total[1m])`
- **Kubernetes Replicas** (stat) — `kube_deployment_status_replicas`
- **CPU Usage Distribution** (bargauge) — средний CPU за 1 мин
- **System Health** (stat) — CPU Load vs Predicted Load
- **Scaling Events** (timeseries) — `changes(kube_deployment_status_replicas[5m])`

## Требования

- Python 3.11+
- Docker
- k3s (или любой Kubernetes)
- kubectl, Helm 3.x

## Установка и запуск

```bash
# Клонировать
git clone https://github.com/MrJonatans/AutoScaler.git
cd AutoScaler

# Установить все зависимости (для разработки)
pip install -r requirements.txt

# Или раздельно:
pip install -r requirements-app.txt   # для app
pip install -r requirements-predictor.txt  # для predictor
```

## Обучение модели

```bash
# Сгенерировать синтетические данные (14 дней)
python scripts/generate_data.py
# → data.csv

# Или использовать Azure trace (30 дней):
# 1. Скачать azure_v2 через datacentertracesdatasets-cli
# 2. Конвертировать:
python scripts/prepare_azure_data.py
# → data.csv (5-min → 1-min интерполяция)

# Обучить модель
python -m src.ml.train
# → model.pth, scaler.pkl, model_evaluation.png

# Визуализировать данные
python scripts/visualize_data.py
# → data_visualization.png
```

### Сбор реальных метрик из Prometheus

```bash
# Собрать CPU метрики за N часов
python scripts/collect_live_data.py --hours 4 --output live_data.csv
```

### Основные параметры Helm

```yaml
# values.yaml (ключевые настройки)

# HPA
hpa:
  useCurrentCpu: true          # Добавить cpu_usage_percent как вторую метрику
  currentCpuThreshold: "40"    # Порог для current CPU
  metrics:
    predicted_cpu: "30"        # Целевое значение predicted_cpu

# Predictor (в кластере — отключён, работает на хосте)
predictor:
  enabled: false

# Prometheus adapter (external metrics)
prometheusAdapter:
  enabled: true
```

```bash
# Пример: только predicted_cpu, без current CPU
helm upgrade autoscaler ./helm/autoscaler -n autoscaling-ns \
  --set hpa.useCurrentCpu=false
```

## Нагрузочное тестирование

```bash
# Классический тест с ramp-up/burst
python tests/integration/load_test.py --concurrency 10 --burst-concurrency 15

# CSV-driven: воспроизводит паттерн CPU из data.csv
python tests/integration/load_test_csv.py --csv data.csv --speed 60

# С синхронизацией по времени (time-sync)
python tests/integration/load_test_csv.py --csv data_scaled.csv --speed 1 --time-sync
```

## Unit тесты

```bash
export PYTHONPATH=/home/pepe/Repos/AutoScaler

# Тесты ML модели
pytest tests/unit/test_model.py -v

# Тесты предсказателя
pytest src/scaler/test_predictor.py -v
```

## Доступ к сервисам

| Сервис | URL | Логин |
|--------|-----|-------|
| FastAPI App | http://192.168.31.41:30080 | — |
| Prometheus | http://192.168.31.41:30909 | — |
| Grafana | http://192.168.31.41:30300 | admin / admin |
| Predictor (host) | http://localhost:8001 | — |

## Лицензия

Смотрите файл LICENSE.
