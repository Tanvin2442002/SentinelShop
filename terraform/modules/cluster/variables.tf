variable "cluster_name" {
  type = string
}

variable "agents" {
  type = number
}

variable "registry_name" {
  type    = string
  default = "shop-tf-registry"
}

variable "registry_port" {
  type = number
}
