from flask import Flask, jsonify, request, Response
from datetime import datetime
import socket
import os
import pika
import json

from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

orders = []

#################################################
# RabbitMQ Configuration
#################################################

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq.default.svc.cluster.local")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "user")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "password")

#################################################
# Prometheus Metrics
#################################################

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

#################################################
# RabbitMQ Publisher
#################################################

def publish_order(order):

    credentials = pika.PlainCredentials(
        RABBITMQ_USER,
        RABBITMQ_PASSWORD
    )

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            credentials=credentials
        )
    )

    channel = connection.channel()

    channel.queue_declare(queue="orders")

    channel.basic_publish(
        exchange="",
        routing_key="orders",
        body=json.dumps(order)
    )

    connection.close()

    RABBITMQ_PUBLISH_TOTAL.inc()

#################################################
# Routes
#################################################

@app.route("/")
def home():
    return jsonify({
        "service": "order-api",
        "status": "running",
        "hostname": socket.gethostname(),
        "version": os.getenv("APP_VERSION", "v1")
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

    data = request.get_json()

    order = {
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)