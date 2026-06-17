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

orders = []
idempotency_store = {}

circuit_breaker = {
    "state": "closed",
    "failure_count": 0,
    "failure_threshold": 3,
    "opened_at": None,
    "recovery_timeout": 30
}

RABBITMQ_HOST = os.getenv(
    "RABBITMQ_HOST",
    "rabbitmq.rabbitmq.svc.cluster.local"
)

RABBITMQ_USER = os.getenv("RABBITMQ_USER", "user")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "password")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "orders")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

PUSHGATEWAY_URL = os.getenv(
    "PUSHGATEWAY_URL",
    "pushgateway.monitoring.svc.cluster.local:9091"
)

ORDERS_CREATED_TOTAL = Counter(
    "orders_created_total",
    "Total number of orders created"
)

ORDERS_IN_MEMORY = Gauge(
    "orders_in_memory",
    "Current number of orders stored in memory"
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

        print(
            "Metrics pushed to Pushgateway",
            flush=True
        )

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


def publish_order(order, max_retries=5, retry_delay=3):
    if is_circuit_open():
        print(
            "Circuit breaker is OPEN. "
            "Skipping RabbitMQ publish.",
            flush=True
        )

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
                body=json.dumps(order),
                properties=pika.BasicProperties(
                    delivery_mode=2
                )
            )

            connection.close()

            RABBITMQ_PUBLISH_TOTAL.inc()
            record_publish_success()
            push_metrics()

            print(
                f"RabbitMQ publish successful "
                f"for order_id={order.get('id')} "
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
        "version": os.getenv("APP_VERSION", "24-pushgateway"),
        "circuit_breaker": circuit_breaker,
        "pushgateway": PUSHGATEWAY_URL
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


@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "orders": orders,
        "count": len(orders),
        "circuit_breaker": circuit_breaker
    })


@app.route("/orders", methods=["POST"])
def create_order():
    idempotency_key = request.headers.get("Idempotency-Key")

    if idempotency_key and idempotency_key in idempotency_store:
        return jsonify({
            "message": "Duplicate request ignored",
            "order": idempotency_store[idempotency_key],
            "circuit_breaker": circuit_breaker
        }), 200

    data = request.get_json() or {}

    order = {
        "event_type": "manual_order_created",
        "source": "order-api",
        "id": len(orders) + 1,
        "product": data.get("product"),
        "quantity": data.get("quantity"),
        "idempotency_key": idempotency_key,
        "created_at": datetime.utcnow().isoformat()
    }

    orders.append(order)

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    ORDERS_CREATED_TOTAL.inc()
    ORDERS_IN_MEMORY.set(len(orders))
    push_metrics()

    published = publish_order(order)

    if not published:
        return jsonify({
            "message": "Order created locally but RabbitMQ publish failed",
            "order": order,
            "circuit_breaker": circuit_breaker
        }), 503

    return jsonify({
        "message": "Order created",
        "order": order,
        "circuit_breaker": circuit_breaker
    }), 201


@app.route("/webhooks/woocommerce/order", methods=["POST"])
def woocommerce_order_webhook():
    data = request.get_json() or {}

    woocommerce_order_id = data.get("id")
    idempotency_key = request.headers.get("Idempotency-Key")

    if not idempotency_key and woocommerce_order_id:
        idempotency_key = f"woocommerce-order-{woocommerce_order_id}"

    if idempotency_key and idempotency_key in idempotency_store:
        return jsonify({
            "message": "Duplicate WooCommerce order ignored",
            "order": idempotency_store[idempotency_key],
            "circuit_breaker": circuit_breaker
        }), 200

    line_items = data.get("line_items", [])
    billing = data.get("billing", {})

    order = {
        "event_type": "woocommerce_order_created",
        "source": "woocommerce",
        "id": len(orders) + 1,
        "woocommerce_order_id": woocommerce_order_id,
        "status": data.get("status"),
        "currency": data.get("currency"),
        "total": data.get("total"),
        "customer_email": billing.get("email"),
        "customer_name": (
            billing.get("first_name", "") + " " +
            billing.get("last_name", "")
        ).strip(),
        "items": [
            {
                "product_id": item.get("product_id"),
                "name": item.get("name"),
                "quantity": item.get("quantity"),
                "total": item.get("total")
            }
            for item in line_items
        ],
        "idempotency_key": idempotency_key,
        "created_at": datetime.utcnow().isoformat()
    }

    orders.append(order)

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    ORDERS_CREATED_TOTAL.inc()
    ORDERS_IN_MEMORY.set(len(orders))
    push_metrics()

    published = publish_order(order)

    if not published:
        return jsonify({
            "message": (
                "WooCommerce order received locally "
                "but RabbitMQ publish failed"
            ),
            "order": order,
            "circuit_breaker": circuit_breaker
        }), 503

    return jsonify({
        "message": "WooCommerce order received",
        "order": order,
        "circuit_breaker": circuit_breaker
    }), 201


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )