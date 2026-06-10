from flask import Flask, jsonify, request, Response
from datetime import datetime
import socket
import os
import pika
import json

from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST


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

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq.rabbitmq.svc.cluster.local")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "user")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "password")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "orders")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))

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


def publish_order(order):
    credentials = pika.PlainCredentials(
        RABBITMQ_USER,
        RABBITMQ_PASSWORD
    )

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=credentials
        )
    )

    channel = connection.channel()

    channel.queue_declare(
        queue=RABBITMQ_QUEUE,
        durable=False
    )

    channel.basic_publish(
        exchange="",
        routing_key=RABBITMQ_QUEUE,
        body=json.dumps(order)
    )

    connection.close()
    RABBITMQ_PUBLISH_TOTAL.inc()


@app.route("/")
def home():
    return jsonify({
        "service": "order-api",
        "status": "running",
        "hostname": socket.gethostname(),
        "version": os.getenv("APP_VERSION", "v3")
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    })


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/orders", methods=["GET"])
def get_orders():
    return jsonify({
        "orders": orders,
        "count": len(orders)
    })


@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json() or {}

    order = {
        "event_type": "manual_order_created",
        "source": "order-api",
        "id": len(orders) + 1,
        "product": data.get("product"),
        "quantity": data.get("quantity"),
        "created_at": datetime.utcnow().isoformat()
    }

    orders.append(order)

    ORDERS_CREATED_TOTAL.inc()
    ORDERS_IN_MEMORY.set(len(orders))

    publish_order(order)

    return jsonify({
        "message": "Order created",
        "order": order
    }), 201


@app.route("/webhooks/woocommerce/order", methods=["POST"])
def woocommerce_order_webhook():
    data = request.get_json() or {}

    line_items = data.get("line_items", [])
    billing = data.get("billing", {})

    order = {
        "event_type": "woocommerce_order_created",
        "source": "woocommerce",
        "id": len(orders) + 1,
        "woocommerce_order_id": data.get("id"),
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
        "created_at": datetime.utcnow().isoformat()
    }

    orders.append(order)

    ORDERS_CREATED_TOTAL.inc()
    ORDERS_IN_MEMORY.set(len(orders))

    publish_order(order)

    return jsonify({
        "message": "WooCommerce order received",
        "order": order
    }), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)