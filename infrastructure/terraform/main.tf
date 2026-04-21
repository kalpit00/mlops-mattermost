resource "openstack_networking_secgroup_v2" "cluster" {
  name        = "${var.prefix}-sg"
  description = "Security group for Mattermost MLOps node."
}

resource "openstack_networking_secgroup_rule_v2" "ssh" {
  for_each          = toset(var.security_group_cidrs)
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.cluster.id
}

resource "openstack_networking_secgroup_rule_v2" "http" {
  for_each          = toset(var.security_group_cidrs)
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.cluster.id
}

resource "openstack_networking_secgroup_rule_v2" "https" {
  for_each          = toset(var.security_group_cidrs)
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 443
  port_range_max    = 443
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.cluster.id
}

locals {
  use_existing_instance = trimspace(var.existing_instance_id) != ""
  # Nova server UUID: either supplied (manual VM) or created by Terraform below.
  cluster_instance_id = local.use_existing_instance ? trimspace(var.existing_instance_id) : openstack_compute_instance_v2.cluster_node[0].id
}

resource "openstack_compute_instance_v2" "cluster_node" {
  count = local.use_existing_instance ? 0 : 1

  name       = "${var.prefix}-node-1"
  image_name = var.image_name
  # Blazar flavor:instance leases register a dedicated Nova flavor whose ID is the reservation UUID
  # (see `openstack flavor list` → name `reservation:<uuid>`). Using a small flavor when only leased capacity exists often yields
  # "No valid host" when only leased capacity exists.
  flavor_name = trimspace(var.reservation_id) == "" ? var.flavor_name : null
  flavor_id   = trimspace(var.reservation_id) != "" ? var.reservation_id : null
  key_pair    = var.keypair_name

  security_groups = [openstack_networking_secgroup_v2.cluster.name]

  network {
    name = var.network_name
  }
}

data "openstack_compute_instance_v2" "existing" {
  count = local.use_existing_instance ? 1 : 0
  id    = trimspace(var.existing_instance_id)
}

resource "openstack_blockstorage_volume_v3" "data" {
  name = "${var.prefix}-data"
  size = var.volume_size_gb
}

resource "openstack_compute_volume_attach_v2" "data_attach" {
  instance_id = local.cluster_instance_id
  volume_id   = openstack_blockstorage_volume_v3.data.id
}

resource "openstack_networking_floatingip_v2" "public_ip" {
  pool = var.external_network_name
}

# Provider v3+ removed openstack_compute_floatingip_associate_v2; use Neutron association by port_id.
# device_id alone matches the VM's primary port (works for Terraform-created and manually created instances).
data "openstack_networking_port_v2" "cluster_node_sharednet" {
  device_id = local.cluster_instance_id
}

resource "openstack_networking_floatingip_associate_v2" "associate" {
  # Provider expects the floating IP *address* (e.g. 129.x.x.x), not the Neutron FIP id — using .id triggers a bad lookup.
  floating_ip = openstack_networking_floatingip_v2.public_ip.address
  port_id     = data.openstack_networking_port_v2.cluster_node_sharednet.id
}
