def runCheck(String name, String target) {
    sh """#!/bin/bash
set -o pipefail
mkdir -p "${env.WORKSPACE}@tmp/reports"
make ${target} 2>&1 | tee "${env.WORKSPACE}@tmp/reports/${name}.log"
"""
}

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '3'))
    }

    environment {
        REGISTRY = 'localhost:5000'
        GITOPS_DIR = '/home/mist/Documents/Projects/sentinelShop-gitops'
    }

    stages {
        stage('Info') {
            steps {
                sh 'rm -rf "${WORKSPACE}@tmp/reports"; git log -1 --oneline; make --version | head -1; docker --version'
            }
        }

        stage('Secrets') {
            steps { script { runCheck('secrets', 'secrets') } }
        }

        stage('Static checks') {
            parallel {
                stage('Dockerfile lint') { steps { script { runCheck('lint', 'lint') } } }
                stage('SAST')            { steps { script { runCheck('sast', 'sast') } } }
                stage('Config scan')     { steps { script { runCheck('config-scan', 'scan-config') } } }
            }
        }

        stage('Prepare') {
            steps { sh 'make env' }
        }

        stage('Build') {
            steps { script { runCheck('build', 'build') } }
        }

        stage('Image scan') {
            steps { script { runCheck('image-scan', 'scan-images') } }
        }

        stage('Push') {
            steps { script { runCheck('push', 'push') } }
        }

        stage('GitOps') {
            steps { script { runCheck('gitops', 'gitops') } }
        }
    }

    post {
        always {
            sh 'mkdir -p reports && cp -r "${WORKSPACE}@tmp/reports/." reports/ 2>/dev/null || true'
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
        }
        success { echo 'Pipeline passed: images built, scanned and pushed.' }
        failure { echo 'Pipeline failed: see the first red stage.' }
        cleanup { cleanWs(deleteDirs: true, notFailBuild: true) }
    }
}