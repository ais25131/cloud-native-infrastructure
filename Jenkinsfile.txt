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

        stage('Import image to MicroK8s') {
            steps {
                sh '''
                microk8s ctr image import kubernetes/apps/order-api/order-api.tar
                '''
            }
        }

        stage('Restart order-api deployment') {
            steps {
                sh '''
                microk8s kubectl rollout restart deployment order-api
                microk8s kubectl rollout status deployment order-api
                '''
            }
        }

        stage('Check pods') {
            steps {
                sh '''
                microk8s kubectl get pods
                microk8s kubectl get svc
                '''
            }
        }
    }
}