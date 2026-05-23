terraform {
  required_providers {
    local = {
      source = "hashicorp/local"
    }
  }
}

resource "local_file" "vagrantfile" {
  filename = "${path.module}/Vagrantfile"

  content = templatefile("${path.module}/templates/Vagrantfile.tpl", {
    vms = var.vms
  })
}

resource "terraform_data" "vagrant_up" {
  depends_on = [
    local_file.vagrantfile
  ]

  triggers_replace = [
    local_file.vagrantfile.content_sha1
  ]

  # Τρέχει στο tofu apply
  provisioner "local-exec" {
    working_dir = path.module
    command     = "vagrant up"
  }

  # Τρέχει στο tofu destroy
  provisioner "local-exec" {
    working_dir = path.module
    when        = destroy
    command     = "vagrant destroy -f"
  }
}