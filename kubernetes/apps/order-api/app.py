from flask import Flask, jsonify, request
from datetime import datetime
import socket
import os
import pika
import json

app = Flask(__name__)

orders = []

#################################################
# RabbitMQ Configuration
#################################################

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")

#################################################
# RabbitMQ Publisher
#################################################

def publish_order(order):

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST)
    )

    channel = connection.channel()

    channel.queue_declare(queue="orders")

    channel.basic_publish(
        exchange="",
        routing_key="orders",
        body=json.dumps(order)
    )

    connection.close()

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

    #################################################
    # Publish to RabbitMQ
    #################################################

    publish_order(order)

    return jsonify({
        "message": "Order created",
        "order": order
    }), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)