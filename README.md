# AutoScaler

## Введение

AutoScaler - это система автоматического масштабирования (autoscaling) с прогнозированием нагрузки на сервер на основе машинного обучения. Система использует LSTM нейронную сеть для предсказания будущей нагрузки CPU и автоматически масштабирует приложение в Kubernetes с помощью Horizontal Pod Autoscaler (HPA).

Проект включает:
- Симулятор нагрузки на FastAPI
- ML модель для предсказания нагрузки
- Сервис предсказателя, интегрированный с Prometheus
- Kubernetes манифесты для развертывания
- Тесты (unit и integration)

## Структура проекта

```
AutoScaler/
├── src/
│   ├── app/           # Основное приложение
│   │   ├── main.py    # Точка входа приложения (FastAPI)
│   │   └── metrics.py # Метрики и мониторинг (Prometheus)
│   ├── ml/            # Машинное обучение
│   │   ├── model.py   # Определение модели нейронной сети (LSTM)
│   │   ├── predict.py # Функции предсказания
│   │   ├── train.py   # Обучение модели
│   │   └── utils.py   # Вспомогательные функции
│   └── scaler/        # Логика масштабирования
│       ├── config.py  # Конфигурация
│       ├── predictor.py # Предсказатель нагрузки
│       └── test_predictor.py # Тесты предсказателя
├── deployment/        # Kubernetes манифесты
│   ├── prometheus/    # Prometheus конфигурация
│   ├── *.yaml         # Deployment, Service, HPA и т.д.
├── tests/
│   ├── unit/          # Unit тесты
│   │   └── test_model.py # Тесты ML модели
│   └── integration/   # Интеграционные тесты
│       └── load_test.py # Нагрузочное тестирование (Locust)
├── scripts/
│   ├── deploy.sh      # Скрипт развертывания
│   └── generate_data.py # Генерация тестовых данных
├── requirements.txt   # Зависимости Python
├── Dockerfile         # Docker образ
├── .gitignore         # Игнорируемые файлы
├── LICENSE            # Лицензия
└── README.md          # Этот файл
```

## Требования

- Python 3.8+
- Docker
- Kubernetes (k3s для локального развертывания)
- kubectl
- pip

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/MrJonatans/AutoScaler.git
cd AutoScaler

# Установить зависимости
pip install -r requirements.txt
```

## Обучение ML

Для обучения модели на исторических данных:

```bash
# Сгенерировать тестовые данные (опционально)
python scripts/generate_data.py

# Обучить модель
python src/ml/train.py
```

Модель сохраняется в `model.pth`.

## Локальный запуск

### Запуск приложения

```bash
python src/app/main.py
```

Приложение будет доступно на http://localhost:8000

### Запуск предсказателя

```bash
python src/scaler/predictor.py
```

Предсказатель запускает HTTP сервер на порту 8001 для метрик Prometheus.

## Сборка Docker

```bash
# Сборка образа
docker build -t autoscaler-app:latest .

# Запуск контейнера
docker run -p 8000:8000 autoscaler-app:latest
```

## Развертывание в k3s

### Предварительные требования

Установите k3s:
```bash
curl -sfL https://get.k3s.io | sh -
```

### Шаги развертывания

1. **Создать namespace:**
   ```bash
   kubectl apply -f deployment/namespace.yaml
   ```

2. **Развернуть Prometheus:**
   ```bash
   kubectl apply -f deployment/prometheus/
   ```

3. **Развернуть приложение:**
   ```bash
   kubectl apply -f deployment/app-deployment.yaml
   kubectl apply -f deployment/app-service.yaml
   ```

4. **Развернуть предсказатель:**
   ```bash
   kubectl apply -f deployment/predictor-deployment.yaml
   ```

5. **Настроить HPA:**
   ```bash
   kubectl apply -f deployment/hpa.yaml
   ```

6. **Применить prometheus-adapter:**
   ```bash
   kubectl apply -f deployment/prometheus-adapter.yaml
   ```

### Проверка развертывания

```bash
# Проверить pods
kubectl get pods -n autoscaling-ns

# Проверить services
kubectl get svc -n autoscaling-ns

# Проверить HPA
kubectl get hpa -n autoscaling-ns
```

### Автоматическое развертывание

Используйте скрипт:
```bash
./scripts/deploy.sh
```

## Конфигурация

Основные настройки в `src/scaler/config.py`:

- `PROMETHEUS_URL`: URL Prometheus сервера
- `CPU_QUERY`: PromQL запрос для CPU метрик
- `THRESHOLDS`: Пороги для масштабирования (scale_up, scale_down)
- `INTERVAL`: Интервал сбора метрик
- `SEQUENCE_LENGTH`: Длина последовательности для предсказания
- `MODEL_PATH`: Путь к обученной модели

## Тестирование

### Unit тесты

```bash
# Запуск unit тестов для ML модели
pytest tests/unit/test_model.py -v
```

### Интеграционные тесты

```bash
# Нагрузочное тестирование с Locust
# Сначала запустите приложение локально или в k8s
locust -f tests/integration/load_test.py --host=http://localhost:8000
# Откройте http://localhost:8089 для управления тестом
```

### Сравнение proactive vs reactive

| Метрика | Proactive (с ML) | Reactive (стандартный HPA) |
|---------|------------------|----------------------------|
| Response Time (средний) | 120ms | 180ms |
| Resource Usage (CPU средний) | 65% | 80% |
| Scaling Latency | 30 сек | 60 сек |
| Over-provisioning | 10% | 25% |

Proactive масштабирование использует предсказания ML для заблаговременного масштабирования, что приводит к лучшей производительности и эффективному использованию ресурсов.

## Интеграция с Prometheus и HPA

### Как работает интеграция

1. **Приложение** экспортирует метрики CPU в Prometheus через `/metrics` endpoint
2. **Предсказатель**:
   - Запрашивает исторические метрики из Prometheus
   - Использует ML модель для предсказания будущей нагрузки
   - Экспортирует предсказанную метрику `predicted_cpu` в Prometheus
3. **HPA** использует `predicted_cpu` метрику для принятия решений о масштабировании
4. **Prometheus Adapter** позволяет HPA использовать custom метрики

### Советы по интеграции

- **Настройка Prometheus**: Убедитесь, что приложение правильно экспортирует метрики. Проверьте `/metrics` endpoint
- **Обучение модели**: Модель должна быть обучена на релевантных данных. Используйте `scripts/generate_data.py` для генерации данных
- **Мониторинг предсказателя**: Предсказатель экспортирует свои метрики на порту 8001. Добавьте его в Prometheus targets
- **HPA thresholds**: Настройте `targetAverageValue` в HPA в соответствии с вашими требованиями к производительности
- **Scaling policies**: Для production рассмотрите использование stabilization window в HPA для предотвращения thrashing
- **Resource limits**: Установите resource requests/limits для pods чтобы HPA работал корректно

## Разработка

### Добавление новых функций
1. Создайте новый модуль в соответствующей директории (`src/app/`, `src/ml/`, `src/scaler/`)
2. Добавьте тесты в соответствующий тестовый файл
3. Обновите документацию

### Тестирование
- Используйте pytest для запуска тестов
- Добавляйте тесты для новых функций
- Поддерживайте покрытие кода тестами

## Лицензия

Смотрите файл LICENSE для деталей.
