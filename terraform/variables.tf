variable aws_region {
    type = list(string)
    description = "Region for AWS resoruces"
}

variable vpc_cidr {
  type = list(string)
  description = "valid subnets to assign to server"
}

variable subnet_cidr {
  type = list(string)
  description = "valid subnets to assign to server"
}

variable prosimo_cidr {
  type = list(string)
  description = "valid subnets to assign to server"
}

variable private_ip {
  description = "Static Private IP"
  type = list(string)
}



variable subscription {
  type = string
  description = "azure subscription id"
}

variable client {
  type = string
  description = "azure client id"
}

variable clientsecret {
  type = string
  description = "azure client secret"
}

variable tenantazure {
  type = string
  description = "azure tenant id"
}

variable cloud_type {
  type = string

}

variable "US_East_FrontEnd" {
  type = map(object({
    aws_vpc_name                = string
    igw_name                    = string
    rt_name                     = string
    aws_subnet_name             = string
    private_ip                  = string
    aws_ec2_name                = string
    aws_ec2_key_pair_name       = string
    aws_vpc_cidr                = string
    aws_subnet_cidr             = string
  }))
}

variable "EU_West_FrontEnd" {
  type = map(object({
    aws_vpc_name                = string
    igw_name                    = string
    rt_name                     = string
    aws_subnet_name             = string
    private_ip                  = string
    app_fqdn                    = string
    aws_ec2_name                = string
    aws_ec2_key_pair_name       = string
    aws_vpc_cidr                = string
    aws_subnet_cidr             = string
  }))
}

variable "North_EU_AppSvcs_VNets" {
  type = map(object({
    azure_resource_group        = string
    azure_location              = string
    azure_vnet_name             = string
    azure_subnet_name           = string
    azure_instance_name         = string
    azure_server_key_pair_name  = string
    azure_private_ip            = string
    azure_vm_size               = string
    azure_admin_username        = string
    azure_subnet_cidr           = string
    azure_vnet_cidr             = string
    azure_admin_password        = string
    enable_peering              = bool

  }))
}

variable "North_US_AppSvcs_VNets" {
  type = map(object({
    azure_resource_group        = string
    azure_location              = string
    azure_vnet_name             = string
    azure_subnet_name           = string
    azure_instance_name         = string
    azure_server_key_pair_name  = string
    azure_private_ip            = string
    azure_vm_size               = string
    azure_admin_username        = string
    azure_subnet_cidr           = string
    azure_vnet_cidr             = string
    azure_admin_password        = string
    enable_peering              = bool

  }))
}

variable "GCP_EU_North" {
  description = "Map of GCP instances and networking configuration per VPC"
  type = map(object({
    gcp_region             = string
    gcp_zone               = string
    ssh_user               = string
    startup_script         = string

    gcp_vpc_name           = string
    gcp_subnet_name        = string
    gcp_private_ip         = string
    gcp_app_fqdn           = string
    gcp_instance_name      = string
    gcp_vm_key_pair_name   = string
    gcp_vpc_cidr           = string
    gcp_subnet_cidr        = string

    labels = map(string)
  }))
}

variable "projectid" {
  type = string
}

variable "instruqt_id" {
  type        = string
  description = "Unique ID assigned to each Instruqt participant"
}

variable "route53_domain_name" {
  description = "The domain name for the private hosted zone"
  type        = string
  default     = "infoblox.local"
}

variable "enable_dns_records" {
  description = "Enable creation of DNS records in the private hosted zone"
  type        = bool
  default     = false
}

variable "target_vpc_name" {
  description = "The name of the VPC to associate with the Route 53 Private Hosted Zone (looked up via the 'Name' tag)"
  type        = string
  default     = "WebSvcsProdEu1"
}
