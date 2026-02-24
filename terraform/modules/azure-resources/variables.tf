## Input variable definitions
# Azure

variable "azure_resource_group" {
  description = "Name of Resource Group"
  type        = string
}

variable "azure_location" {
  description = "Location of Resource Group"
  type        = string
}

variable "azure_vnet_name" {
  description = "Name of VPC"
  type        = string
}

variable "azure_private_ip" {
  description = "Private IP for VM"
  type       = string
}

variable "azure_server_key_pair_name" {
  description = "SSH Key Name"
  type        = string
}

variable "azure_vnet_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "azure_subnet_cidr" {
  description = "Subnet CIDR"
  type        = string
  default     = "10.0.1.0/24"
}

variable "azure_subnet_name" {
  description = "Name of Subnet"
  type        = string
}

variable "azure_instance_name" {
  description = "Name of the Instance"
  type        = string
}

variable "azure_vm_size" {
  description = "VM Size of the Instance"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "azure_admin_username" {
  description = "Admin Username for Instance"
  type        = string
}

variable "azure_admin_password" {
  description = "Admin Password for Instance"
  type        = string
}

# Add the enable_peering flag to your module
variable "enable_peering" {
  type    = bool
  default = false  # Default to false if not specified
}

variable "tags" {
  description = "Common tags applied to all Azure resources"
  type        = map(string)
  default = {
    Environment   = "Production"
    Owner         = "iracic@infoblox.com"
    Project       = "Infoblox-POC"
    ManagedBy     = "Terraform-TME"
  }
}
