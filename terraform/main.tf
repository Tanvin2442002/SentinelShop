module "cluster" {
  source        = "./modules/cluster"
  cluster_name  = var.cluster_name
  agents        = var.agents
  registry_port = var.registry_port
}

module "platform" {
  source     = "./modules/platform"
  depends_on = [module.cluster]
}
