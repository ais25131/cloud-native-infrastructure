from flask import Flask, jsonify, request, Response
from datetime import datetime
import socket
import os
import pika
import json
import time

from prometheus_client import (
    Counter,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    push_to_gateway
)


def load_vault_env_file(path="/vault/secrets/rabbitmq"):
    if not os.path.exists(path):
        return

    with open(path, "r") as file:
        for line in file:
            line = line.strip()

            if not line or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ[key] = value


load_vault_env_file()

app = Flask(__name__)

events = []
orders = []
idempotency_store = {}

circuit_breaker = {
    "state": "closed",
    "failure_count": 0,
    "failure_threshold": 3,
    "opened_at": None,
    "recovery_timeout": 30
}

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq.rabbitmq.svc.cluster.local")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "user")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "password")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "orders")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

PUSHGATEWAY_URL = os.getenv(
    "PUSHGATEWAY_URL",
    "pushgateway.monitoring.svc.cluster.local:9091"
)

EVENTS_RECEIVED_TOTAL = Counter(
    "order_api_events_received_total",
    "Total number of events received by Order API",
    ["event_type"]
)

EVENTS_PUBLISHED_TOTAL = Counter(
    "order_api_events_published_total",
    "Total number of events published to RabbitMQ",
    ["event_type"]
)

EVENTS_FAILED_TOTAL = Counter(
    "order_api_events_failed_total",
    "Total number of events failed to publish",
    ["event_type"]
)

ORDERS_CREATED_TOTAL = Counter(
    "orders_created_total",
    "Total number of orders created"
)

ORDERS_IN_MEMORY = Gauge(
    "orders_in_memory",
    "Current number of orders stored in memory"
)

EVENTS_IN_MEMORY = Gauge(
    "events_in_memory",
    "Current number of events stored in memory"
)

RABBITMQ_PUBLISH_TOTAL = Counter(
    "rabbitmq_publish_total",
    "Total number of messages published to RabbitMQ"
)

RABBITMQ_PUBLISH_RETRY_TOTAL = Counter(
    "rabbitmq_publish_retry_total",
    "Total number of RabbitMQ publish retry attempts"
)

RABBITMQ_PUBLISH_FAILED_TOTAL = Counter(
    "rabbitmq_publish_failed_total",
    "Total number of failed RabbitMQ publish operations"
)


def push_metrics():
    try:
        push_to_gateway(
            PUSHGATEWAY_URL,
            job="order-api"
        )
        print("Metrics pushed to Pushgateway", flush=True)

    except Exception as error:
        print(
            f"Failed to push metrics to Pushgateway: {error}",
            flush=True
        )


def is_circuit_open():
    if circuit_breaker["state"] != "open":
        return False

    elapsed = time.time() - circuit_breaker["opened_at"]

    if elapsed >= circuit_breaker["recovery_timeout"]:
        circuit_breaker["state"] = "half-open"
        print("Circuit breaker moved to HALF-OPEN", flush=True)
        return False

    return True


def record_publish_success():
    circuit_breaker["state"] = "closed"
    circuit_breaker["failure_count"] = 0
    circuit_breaker["opened_at"] = None
    print("Circuit breaker CLOSED", flush=True)


def record_publish_failure():
    circuit_breaker["failure_count"] += 1

    if circuit_breaker["failure_count"] >= circuit_breaker["failure_threshold"]:
        circuit_breaker["state"] = "open"
        circuit_breaker["opened_at"] = time.time()
        print("Circuit breaker OPEN", flush=True)


def publish_event(event, max_retries=5, retry_delay=3):
    event_type = event.get("event_type", "unknown")

    if is_circuit_open():
        print("Circuit breaker is OPEN. Skipping RabbitMQ publish.", flush=True)

        EVENTS_FAILED_TOTAL.labels(event_type=event_type).inc()
        RABBITMQ_PUBLISH_FAILED_TOTAL.inc()
        push_metrics()

        return False

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            credentials = pika.PlainCredentials(
                RABBITMQ_USER,
                RABBITMQ_PASSWORD
            )

            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                    connection_attempts=1,
                    retry_delay=0
                )
            )

            channel = connection.channel()

            channel.queue_declare(
                queue=RABBITMQ_QUEUE,
                durable=True
            )

            channel.basic_publish(
                exchange="",
                routing_key=RABBITMQ_QUEUE,
                body=json.dumps(event),
                properties=pika.BasicProperties(
                    delivery_mode=2
                )
            )

            connection.close()

            EVENTS_PUBLISHED_TOTAL.labels(event_type=event_type).inc()
            RABBITMQ_PUBLISH_TOTAL.inc()
            record_publish_success()
            push_metrics()

            print(
                f"RabbitMQ publish successful "
                f"event_type={event_type} "
                f"event_id={event.get('event_id')} "
                f"attempt={attempt}",
                flush=True
            )

            return True

        except Exception as error:
            last_error = error
            RABBITMQ_PUBLISH_RETRY_TOTAL.inc()
            push_metrics()

            print(
                f"RabbitMQ publish failed. "
                f"Retry {attempt}/{max_retries}. "
                f"Error: {error}",
                flush=True
            )

            if attempt < max_retries:
                time.sleep(retry_delay)

    EVENTS_FAILED_TOTAL.labels(event_type=event_type).inc()
    RABBITMQ_PUBLISH_FAILED_TOTAL.inc()
    record_publish_failure()
    push_metrics()

    print(
        f"RabbitMQ publish permanently failed "
        f"after {max_retries} attempts. "
        f"Last error: {last_error}",
        flush=True
    )

    return False


@app.route("/")
def home():
    return jsonify({
        "service": "order-api",
        "status": "running",
        "hostname": socket.gethostname(),
        "version": os.getenv("APP_VERSION", "25-events-through-order-api"),
        "rabbitmq_host": RABBITMQ_HOST,
        "rabbitmq_queue": RABBITMQ_QUEUE,
        "pushgateway": PUSHGATEWAY_URL,
        "circuit_breaker": circuit_breaker
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    })


@app.route("/metrics")
def metrics():
    return Response(
        generate_latest(),
        mimetype=CONTENT_TYPE_LATEST
    )


@app.route("/events", methods=["POST"])
def receive_event():
    idempotency_key = request.headers.get("Idempotency-Key")
    data = request.get_json() or {}

    event_type = data.get("event_type")

    if not event_type:
        return jsonify({
            "message": "event_type is required"
        }), 400

    if not idempotency_key:
        idempotency_key = data.get("event_id")

    if not idempotency_key:
        idempotency_key = (
            f"{event_type}-"
            f"{data.get('source', 'unknown')}-"
            f"{datetime.utcnow().isoformat()}"
        )

    if idempotency_key in idempotency_store:
        return jsonify({
            "message": "Duplicate event ignored",
            "event": idempotency_store[idempotency_key],
            "circuit_breaker": circuit_breaker
        }), 200

    event = data
    event["event_id"] = idempotency_key
    event["received_by"] = "order-api"
    event["received_at"] = datetime.utcnow().isoformat()

    events.append(event)
    idempotency_store[idempotency_key] = event

    EVENTS_RECEIVED_TOTAL.labels(event_type=event_type).inc()
    EVENTS_IN_MEMORY.set(len(events))

    if event_type == "order_created":
        ORDERS_CREATED_TOTAL.inc()
        ORDERS_IN_MEMORY.set(
            len([
                e for e in events
                if e.get("event_type") == "order_created"
            ])
        )

    push_metrics()

    published = publish_event(event)

    if not published:
        return jsonify({
            "message": "Event received locally but RabbitMQ publish failed",
            "event": event,
            "circuit_breaker": circuit_breaker
        }), 503

    return jsonify({
        "message": "Event received and published",
        "event": event,
        "circuit_breaker": circuit_breaker
    }), 201


@app.route("/events", methods=["GET"])
def get_events():
    return jsonify({
        "events": events,
        "count": len(events),
        "circuit_breaker": circuit_breaker
    })


@app.route("/orders", methods=["GET"])
def get_orders():
    order_events = [
        event for event in events
        if event.get("event_type") == "order_created"
    ]

    return jsonify({
        "orders": order_events,
        "count": len(order_events),
        "circuit_breaker": circuit_breaker
    })


@app.route("/orders", methods=["POST"])
def create_manual_order():
    idempotency_key = request.headers.get("Idempotency-Key")

    if idempotency_key and idempotency_key in idempotency_store:
        return jsonify({
            "message": "Duplicate request ignored",
            "order": idempotency_store[idempotency_key],
            "circuit_breaker": circuit_breaker
        }), 200

    data = request.get_json() or {}

    if not idempotency_key:
        idempotency_key = f"manual-order-{datetime.utcnow().isoformat()}"

    order = {
        "event_type": "order_created",
        "source": "order-api",
        "event_id": idempotency_key,
        "user": {
            "username": data.get("username", "manual")
        },
        "order": {
            "id": len(orders) + 1,
            "status": "manual",
            "total": data.get("total"),
            "currency": data.get("currency", "EUR"),
            "items": data.get("items", []),
            "total_qty": data.get("quantity", 1)
        },
        "created_at": datetime.utcnow().isoformat()
    }

    orders.append(order)
    events.append(order)
    idempotency_store[idempotency_key] = order

    EVENTS_RECEIVED_TOTAL.labels(event_type="order_created").inc()
    ORDERS_CREATED_TOTAL.inc()
    ORDERS_IN_MEMORY.set(len(orders))
    EVENTS_IN_MEMORY.set(len(events))
    push_metrics()

    published = publish_event(order)

    if not published:
        return jsonify({
            "message": "Order created locally but RabbitMQ publish failed",
            "order": order,
            "circuit_breaker": circuit_breaker
        }), 503

    return jsonify({
        "message": "Order created and published",
        "order": order,
        "circuit_breaker": circuit_breaker
    }), 201


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )