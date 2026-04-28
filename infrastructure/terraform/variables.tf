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
  description = <<-EOT
    Blazar **flavor:instance** reservation UUID used as Nova `flavor_id` (Horizon: lease → Reservations → **flavor_id**, e.g. m1.xxlarge on that lease).
    Same value appears in `openstack flavor list` as a flavor named `reservation:<uuid>`.
    When set, `flavor_name` is ignored. Leave empty to create the VM with `flavor_name` only (needs spare capacity).
    Do not confuse with the **lease** id or **project** id — use the reservation row's flavor_id.
  EOT
  type        = string
  default     = ""
}

variable "existing_instance_id" {
  description = <<-EOT
    When non-empty, Terraform does NOT create a VM: it uses this Nova server UUID (manually created in Horizon/CLI, e.g. m1.xxlarge on a Blazar lease).
    Terraform still creates the security group, Cinder volume, volume attach, floating IP, and FIP association.
    Attach the security group named "<prefix>-sg" (same prefix as the prefix variable) to that instance in Horizon or CLI so SSH/HTTP/HTTPS match this stack.
    Leave empty to let Terraform create the instance (uses flavor_name / reservation_id as today).
  EOT
  type        = string
  default     = ""
}

variable "keypair_name" {
  description = "OpenStack keypair name to attach to instance. Set with export TF_VAR_keypair_name (not committed tfvars); see final-sequence.md Phase 1."
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
