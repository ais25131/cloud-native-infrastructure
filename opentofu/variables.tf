variable "vms" {
  description = "list of virtual machines to create"

  type = map(object({
    ip     = string
    role   = string
    memory = number
    cpus   = number
  }))
}