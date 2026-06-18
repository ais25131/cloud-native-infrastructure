![Kubernetes](https://img.shields.io/badge/Kubernetes-1.33-blue)
![Knative](https://img.shields.io/badge/Knative-Serverless-orange)
![ArgoCD](https://img.shields.io/badge/ArgoCD-GitOps-red)
![Vault](https://img.shields.io/badge/Vault-Secrets-black)
![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-orange)
![Grafana](https://img.shields.io/badge/Grafana-Dashboards-yellow)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-Messaging-ff6600)
![MinIO](https://img.shields.io/badge/MinIO-Object_Storage-red)
![ThingsBoard](https://img.shields.io/badge/ThingsBoard-IoT-green)
![Node--RED](https://img.shields.io/badge/Node--RED-Low_Code-8f0000)
![Jenkins](https://img.shields.io/badge/Jenkins-CI%2FCD-red)
![OpenTofu](https://img.shields.io/badge/OpenTofu-IaC-844FBA)
![Ansible](https://img.shields.io/badge/Ansible-Automation-black)

# Cloud Native Infrastructure for an Event-Driven E-Commerce Platform

## Overview

This project implements a cloud-native, event-driven e-commerce infrastructure on Kubernetes.

The platform is centered around a WooCommerce-based WordPress store that produces business events. These events are processed asynchronously through an Order API, RabbitMQ, Knative Eventing, Node-RED, MinIO and ThingsBoard.

The goal of the project is to demonstrate a complete Cloud Native architecture using:

- Kubernetes
- GitOps
- CI/CD
- Serverless workloads
- Event-driven communication
- Secret management
- Monitoring and alerting
- Infrastructure as Code
- Automation

The infrastructure runs on MicroK8s and is managed with ArgoCD.

---

## Architecture

The platform consists of the following components:

- WordPress / WooCommerce
- Order API (Knative Service)
- RabbitMQ
- RabbitmqSource
- Node-RED (Knative Service)
- MinIO
- ThingsBoard
- Vault
- Prometheus
- Grafana
- Jenkins
- ArgoCD

---

## Main Event Flow

The business workflow follows these steps:

1. A user performs an action in WooCommerce.
2. WordPress sends an HTTP event to the Order API.
3. Order API publishes the event to RabbitMQ.
4. RabbitmqSource receives the message from RabbitMQ.
5. Node-RED is automatically scaled up by Knative.
6. Node-RED processes the event.
7. Processed data is stored in MinIO.
8. Telemetry is forwarded to ThingsBoard.

---

## Technologies

| Area                     | Technology                        |
| ------------------------ | --------------------------------- |
| Kubernetes Distribution  | MicroK8s                          |
| GitOps                   | ArgoCD                            |
| Serverless               | Knative Serving                   |
| Eventing                 | Knative Eventing / RabbitmqSource |
| Message Broker           | RabbitMQ                          |
| Workflow Automation      | Node-RED                          |
| Object Storage           | MinIO                             |
| IoT / Telemetry Platform | ThingsBoard                       |
| E-commerce               | WordPress / WooCommerce           |
| Secret Management        | HashiCorp Vault                   |
| Secret Injection         | Vault Agent Injector              |
| Monitoring               | Prometheus                        |
| Visualization            | Grafana                           |
| CI/CD                    | Jenkins                           |
| Container Registry       | DockerHub                         |
| Infrastructure as Code   | OpenTofu                          |
| Automation               | Ansible                           |

---

---

## Cloud Native Patterns Implemented

| Pattern                    | Implementation                                                          |
| -------------------------- | ----------------------------------------------------------------------- |
| Stateless Services         | Order API and Node-RED run as stateless Knative Services                |
| Retry Pattern              | Order API retries RabbitMQ publish failures                             |
| Circuit Breaker            | Order API stops publishing temporarily after repeated failures          |
| Idempotency                | Order API detects duplicate events using event IDs and idempotency keys |
| Event-Driven Architecture  | RabbitMQ decouples producers and consumers                              |
| Async Processing           | WordPress does not wait for Node-RED processing                         |
| Serverless / Scale to Zero | Order API and Node-RED are deployed with Knative                        |
| GitOps                     | ArgoCD continuously synchronizes Kubernetes manifests                   |
| Sidecar Pattern            | Vault Agent Injector injects secrets into workloads                     |

---

## Serverless Components

The following services are deployed as Knative Services:

```text
order-api-knative
node-red-knative
```


Both services support scale-to-zero and are started on demand.


---

## Secret Management

HashiCorp Vault is used as the central secret management system.

Runtime secrets are not stored directly in the application manifests.

Vault is used for:

* RabbitMQ credentials
* MinIO credentials
* Grafana credentials
* Node-RED environment variables
* ThingsBoard access token
* PostgreSQL credentials
* WordPress database credentials

Secrets are injected into workloads using the Vault Agent Injector.


---

## CI/CD Pipeline

CI/CD is implemented with Jenkins.

The Jenkins pipeline performs the following steps:

1. Checkout source code from GitHub
2. Build the Order API Docker image
3. Push the image to DockerHub
4. Update the Knative manifest with the new image tag
5. Commit and push the updated manifest back to GitHub
6. ArgoCD detects the change and deploys it automatically

The Docker image used by the Order API is:

```text
docker.io/ais25131/order-api
```

The Jenkins pipeline updates:

```text
kubernetes/apps/knative/manifests/order-api-knative.yaml
```

The repository is private, so Jenkins uses:

* DockerHub credentials
* GitHub credentials / token

These credentials are stored in Jenkins Credentials and are not committed to the repository.

---

## GitOps Deployment

ArgoCD is used to manage Kubernetes applications.

The cluster is configured with:

```text
Auto Sync
Prune
Self Heal
```

This means that the desired state is stored in Git and ArgoCD continuously reconciles the live cluster with the repository.

Current ArgoCD applications include:

```text
cert-manager
grafana
knative-eventing
kube-state-metrics
minio
node-red-eventing
node-red-knative
order-api-knative
prometheus
pushgateway
rabbitmq
rabbitmq-source
rabbitmq-topology-operator
thingsboard
vault
vault-injector
wordpress
```

---

## Monitoring and Alerting

Prometheus is used for metrics collection.

Grafana is used for dashboards.

Prometheus currently scrapes:

```text
prometheus
pushgateway
rabbitmq
kube-state-metrics
```

The Prometheus configuration also includes alerting rules for application and messaging health.

Implemented alerts:

| Alert                   | Description                                                       |
| ----------------------- | ----------------------------------------------------------------- |
| RabbitMQQueueBacklog    | Triggers when the RabbitMQ queue has more than 5 pending messages |
| OrderAPIPublishFailures | Triggers when Order API fails to publish to RabbitMQ              |
| OrderAPIPublishRetries  | Triggers when Order API retries publishing                        |
| RabbitMQQueueGrowing    | Triggers when the RabbitMQ queue is continuously growing          |

---

## ThingsBoard Integration

ThingsBoard is used to visualize business events as telemetry.

Node-RED forwards processed events to ThingsBoard.

Example event types:

```text
cart_add
order_created
```

A ThingsBoard dashboard export is included in:

```text
integrations/thingsboard/e_shop_events.json
```

---

## MinIO Integration

MinIO is used as object storage.

Node-RED writes processed event data to MinIO.

MinIO is also configured with RabbitMQ notification support through Kubernetes jobs and manifests.

---

## Keycloak

Keycloak integration was implemented during development and remains available in the repository for future Single Sign-On extensions.

The final event workflow uses a custom WordPress plugin for event forwarding.

Keycloak is kept as part of the infrastructure because it can be used later for authentication and identity management.

---

## OpenTofu

OpenTofu is used as the Infrastructure as Code solution of the project.

It provisions the two virtual machines hosting:

- Kubernetes / MicroK8s
- Jenkins

The OpenTofu configuration is stored in:

```text
opentofu/
```

---

## Ansible

Ansible was used to configure and provision the virtual machines.

Implemented roles include:

- argocd
- common
- jenkins
- knative
- kubernetes
- monitoring

The Ansible inventory is stored in:

```text
ansible/inventory.ini
```

The main playbook is:

```text
ansible/site.yml
```

---

## Access URLs

The applications are exposed through local hostnames.

The following hostnames must resolve to the Kubernetes ingress IP through the local hosts file.

| Application | URL |
|------------|-----|
| WordPress | http://wordpress.local |
| Node-RED | http://node-red.local |
| MinIO | http://minio.local |
| MinIO Console | http://minio-console.local |
| RabbitMQ | http://rabbitmq.local |
| ThingsBoard | http://thingsboard.local |
| Vault | http://vault.local |
| Grafana | http://grafana.local |
| Prometheus | http://prometheus.local |
| Jenkins | http://jenkins.local |
| ArgoCD | http://argocd.local |

---

## Manual Configuration Required

This repository does not include real credentials.

After cloning the repository, the following values must be configured manually.

### Jenkins Credentials

Create Jenkins credentials for:

```text
dockerhub
github
```

The `dockerhub` credential is used to push images.

The `github` credential is used to commit updated manifests back to the private repository.

---

### Ansible Passphrase

The file:

```text
ansible/group_vars/all.yml
```

contains a placeholder value:

```yaml
ansible_key_passphrase: "CHANGE_ME"
```

Replace it with the passphrase of the SSH private key used by Ansible.

---

### Vault Secrets

The following secrets must be created in Vault:

```text
secret/data/rabbitmq
secret/data/minio
secret/data/grafana
secret/data/node-red
secret/data/thingsboard
secret/data/wordpress-db
secret/data/pg-secret
```

The exact keys depend on the corresponding Vault injection templates.



---



## Deployment Overview

A typical deployment process consists of:

1. Provisioning the virtual machines with OpenTofu
2. Configuring the hosts using Ansible
3. Deploying applications through ArgoCD
4. Creating the required Vault secrets
5. Configuring Jenkins credentials
6. Running the CI/CD pipeline

---

## Demo Scenario

A simple demo scenario is:

1. Open WordPress at `http://wordpress.local`
2. Add a product to the WooCommerce cart
3. WordPress sends an event to the Order API
4. Order API publishes the event to RabbitMQ
5. RabbitmqSource triggers Node-RED
6. Node-RED processes the event
7. Event data is stored in MinIO
8. Event telemetry appears in ThingsBoard
9. RabbitMQ and Kubernetes metrics are visible in Grafana
10. ArgoCD shows all applications as Synced and Healthy

---
## Validation

The deployment was validated by verifying:

- ArgoCD application health
- Knative scale-to-zero behavior
- RabbitMQ event delivery
- Node-RED event processing
- MinIO object creation
- ThingsBoard telemetry ingestion
- Prometheus alerts
- Grafana dashboards
- Vault secret injection
- Jenkins image build and deployment

---

## Known Limitations

* The repository is private and requires Git credentials for ArgoCD and Jenkins.
* Real credentials are not included in the repository.
* Local domains require manual `hosts` configuration.
* Order API is internal-only and does not expose a public ingress.
* Keycloak is included for future SSO support but is not used in the final event-processing flow.

---

## Future Improvements

Possible improvements include:

* Add automated Vault secret provisioning
* Add Alertmanager integration
* Add direct Order API scraping in Prometheus
* Add more Grafana dashboards
* Add automated integration tests
* Add GitHub webhooks instead of SCM polling
* Extend Keycloak SSO integration
* Add Helm charts for reusable deployment
* Add documentation screenshots under `docs/images`

---

## Conclusion

This project demonstrates a complete Cloud Native infrastructure for an event-driven e-commerce platform.

It combines Kubernetes, Knative, RabbitMQ, Node-RED, MinIO, ThingsBoard, Vault, Prometheus, Grafana, Jenkins and ArgoCD into a single GitOps-based architecture.
The resulting platform demonstrates how modern Cloud Native practices can be combined to build a scalable, observable and event-driven application ecosystem on Kubernetes.

```
```
