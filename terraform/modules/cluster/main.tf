resource "terraform_data" "registry" {
  input = var.registry_name

  provisioner "local-exec" {
    command = "k3d registry create ${var.registry_name} --port 127.0.0.1:${var.registry_port}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "k3d registry delete k3d-${self.input}"
  }
}

resource "terraform_data" "cluster" {
  depends_on       = [terraform_data.registry]
  triggers_replace = [var.cluster_name, var.agents]

  input = {
    cluster  = var.cluster_name
    registry = "k3d-${var.registry_name}"
  }

  provisioner "local-exec" {
    command = "k3d cluster create ${var.cluster_name} --servers 1 --agents ${var.agents} --registry-use k3d-${var.registry_name}:${var.registry_port} --kubeconfig-switch-context=false --wait"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "docker network disconnect k3d-${self.input.cluster} ${self.input.registry} || true; k3d cluster delete ${self.input.cluster}"
  }
}
