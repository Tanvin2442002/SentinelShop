resource "kubernetes_namespace_v1" "shop" {
  metadata {
    name = var.namespace
  }
}

resource "kubernetes_resource_quota_v1" "shop" {
  metadata {
    name      = "shop-quota"
    namespace = kubernetes_namespace_v1.shop.metadata[0].name
  }
  spec {
    hard = {
      "requests.cpu"    = "4"
      "requests.memory" = "6Gi"
      "limits.cpu"      = "8"
      "limits.memory"   = "12Gi"
      "pods"            = "40"
    }
  }
}

resource "kubernetes_limit_range_v1" "shop" {
  metadata {
    name      = "shop-limits"
    namespace = kubernetes_namespace_v1.shop.metadata[0].name
  }
  spec {
    limit {
      type            = "Container"
      default         = { cpu = "500m", memory = "512Mi" }
      default_request = { cpu = "100m", memory = "128Mi" }
    }
  }
}

resource "kubernetes_network_policy_v1" "default_deny" {
  metadata {
    name      = "default-deny"
    namespace = kubernetes_namespace_v1.shop.metadata[0].name
  }
  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }
}
