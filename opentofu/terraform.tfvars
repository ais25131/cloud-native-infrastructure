vms = {

  k8s = {
    ip     = "192.168.56.21"
    role   = "kubernetes"
    memory = 8192
    cpus   = 4
  }

  jenkins = {
    ip     = "192.168.56.22"
    role   = "jenkins"
    memory = 2048
    cpus   = 2
  }
} 