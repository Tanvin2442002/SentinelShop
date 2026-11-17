variable "cluster_name" {
  type    = string
  default = "shop-tf"
}

variable "agents" {
  type    = number
  default = 2
}

variable "registry_port" {
  type    = number
  default = 5001
}
