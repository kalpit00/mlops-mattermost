terraform {
  required_version = ">= 1.5.0"

  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      # 3.x has current builds for darwin_arm64; 2.1.0 can fail plugin handshake on some Macs
      version = "~> 3.0"
    }
  }
}

provider "openstack" {
  cloud = var.openstack_cloud
}
