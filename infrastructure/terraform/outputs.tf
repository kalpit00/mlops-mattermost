output "instance_name" {
  value = openstack_compute_instance_v2.cluster_node.name
}

output "instance_id" {
  value = openstack_compute_instance_v2.cluster_node.id
}

output "floating_ip" {
  value = openstack_networking_floatingip_v2.public_ip.address
}

output "attached_volume_id" {
  value = openstack_blockstorage_volume_v3.data.id
}
