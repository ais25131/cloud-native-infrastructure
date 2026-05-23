pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build order-api image') {
            steps {
                dir('kubernetes/apps/order-api') {
                    sh 'docker build -t order-api:v1 .'
                    sh 'docker save order-api:v1 -o order-api.tar'
                }
            }
        }

        stage('Deploy order-api with Ansible') {
            steps {
                dir('ansible') {
                    sh 'ansible-playbook -i inventory.ini deploy-order-api.yml'
                }
            }
        }

        stage('Check Kubernetes status') {
            steps {
                dir('ansible') {
                    sh '''
                    ansible kubernetes -i inventory.ini -m shell -a "microk8s kubectl get pods -A"
                    '''
                }
            }
        }
    }
}