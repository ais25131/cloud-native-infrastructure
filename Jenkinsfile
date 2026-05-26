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
                    sh '''
                        set -e

                        eval "$(ssh-agent -s)"

                        export SSH_ASKPASS=/var/lib/jenkins/.ssh/askpass.sh
                        export DISPLAY=:0

                        setsid ssh-add /var/lib/jenkins/.ssh/ansible_key

                        ansible-playbook -i inventory.ini deploy-order-api.yml

                        ssh-agent -k
                    '''
                }
            }
        }

        stage('Check Kubernetes status') {
            steps {
                dir('ansible') {
                    sh '''
                        set -e

                        eval "$(ssh-agent -s)"

                        export SSH_ASKPASS=/var/lib/jenkins/.ssh/askpass.sh
                        export DISPLAY=:0

                        setsid ssh-add /var/lib/jenkins/.ssh/ansible_key

                        ansible kubernetes -i inventory.ini -m shell -a "microk8s kubectl get pods -A"

                        ssh-agent -k
                    '''
                }
            }
        }
    }

    post {
        success {
            echo 'Jenkins pipeline completed successfully.'
        }

        failure {
            echo 'Jenkins pipeline failed.'
        }
    }
}