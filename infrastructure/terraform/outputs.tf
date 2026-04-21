output "instance_name" {
  value = local.use_existing_instance ? data.openstack_compute_instance_v2.existing[0].name : openstack_compute_instance_v2.cluster_node[0].name
}

output "instance_id" {
  value = local.cluster_instance_id
}

output "floating_ip" {
  value = openstack_networking_floatingip_v2.public_ip.address
}

output "attached_volume_id" {
  value = openstack_blockstorage_volume_v3.data.id
}

output "security_group_name" {
  value       = openstack_networking_secgroup_v2.cluster.name
  description = "Attach this security group to the instance when using existing_instance_id (manual VM)."
}
