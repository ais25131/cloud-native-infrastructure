pipeline {
    agent any

    environment {
        DOCKER_IMAGE = "docker.io/ais25131/order-api"
        IMAGE_TAG = "${BUILD_NUMBER}"
        KNATIVE_MANIFEST = "kubernetes/apps/knative/manifests/order-api-knative.yaml"
    }

    triggers {
        pollSCM('H/2 * * * *')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build Docker image') {
            steps {
                dir('kubernetes/apps/order-api') {
                    sh '''
                        docker build \
                          -t $DOCKER_IMAGE:$IMAGE_TAG \
                          .
                    '''
                }
            }
        }

        stage('Push Docker image') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        docker push $DOCKER_IMAGE:$IMAGE_TAG
                        docker logout
                    '''
                }
            }
        }

        stage('Update Knative manifest image') {
            steps {
                sh '''
                    sed -i "s|image: docker.io/ais25131/order-api:.*|image: $DOCKER_IMAGE:$IMAGE_TAG|" $KNATIVE_MANIFEST
                    sed -i "s|value: \\".*\\"|value: \\"$IMAGE_TAG\\"|" $KNATIVE_MANIFEST
                '''
            }
        }

        stage('Commit and push manifest') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'github',
                    usernameVariable: 'GIT_USER',
                    passwordVariable: 'GIT_TOKEN'
                )]) {
                    sh '''
                        git config user.name "jenkins"
                        git config user.email "jenkins@local"

                        git add $KNATIVE_MANIFEST

                        if git diff --cached --quiet; then
                            echo "No changes to commit."
                        else
                            git commit -m "Update order-api Knative image to $IMAGE_TAG"
                            git push https://$GIT_USER:$GIT_TOKEN@github.com/ais25131/cloud-native-infrastructure.git HEAD:main
                        fi
                    '''
                }
            }
        }
    }

    post {
        success {
            echo 'CI pipeline completed successfully.'
        }

        failure {
            echo 'CI pipeline failed.'
        }
    }
}