variable "openstack_cloud" {
  description = "Cloud profile name from clouds.yaml."
  type        = string
  default     = "openstack"
}

variable "prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "proj17"
}

variable "image_name" {
  description = "OpenStack image name for the VM."
  type        = string
}

variable "flavor_name" {
  description = "OpenStack flavor name for the VM."
  type        = string
}

variable "reservation_id" {
  description = "Blazar flavor:instance reservation UUID from lease details (same id as the reservation row; `openstack flavor list` shows it as flavor name reservation:<uuid>). When set, used as Nova flavor_id. Leave empty to use flavor_name only (e.g. m1.medium when unleased capacity exists)."
  type        = string
  default     = ""
}

variable "keypair_name" {
  description = "OpenStack keypair name to attach to instance."
  type        = string
}

variable "network_name" {
  description = "Private network name for the instance."
  type        = string
}

variable "external_network_name" {
  description = "External network used for floating IP."
  type        = string
}

variable "volume_size_gb" {
  description = "Cinder volume size in GB."
  type        = number
  default     = 50
}

variable "security_group_cidrs" {
  description = "CIDRs allowed for SSH/HTTP/HTTPS."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
