terraform {
  required_version = ">= 1.4, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.70.0"
    }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = {
      Project   = "InfraLens"
      Purpose   = "DriftSandbox"
      ManagedBy = "Terraform"
      RunId     = var.run_id
    }
  }
}

variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be the expected 12-digit AWS account."
  }
}

variable "region" {
  type = string
}

variable "run_id" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{12}$", var.run_id))
    error_message = "run_id must be a fresh 12-digit hexadecimal identifier."
  }
}

variable "ami_id" {
  type = string
  validation {
    condition     = can(regex("^ami-[a-f0-9]+$", var.ami_id))
    error_message = "ami_id must be an AMI in the selected region."
  }
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
  validation {
    condition     = contains(["t3.micro", "t3.small"], var.instance_type)
    error_message = "This demo only supports t3.micro and t3.small."
  }
}

resource "aws_vpc" "demo" {
  cidr_block           = "10.241.0.0/24"
  enable_dns_support   = true
  enable_dns_hostnames = false
  tags                 = { Name = "infralens-drift-${var.run_id}" }
}

resource "aws_subnet" "demo" {
  vpc_id                  = aws_vpc.demo.id
  cidr_block              = "10.241.0.0/28"
  map_public_ip_on_launch = false
  tags                    = { Name = "infralens-drift-${var.run_id}" }
}

resource "aws_security_group" "demo" {
  name        = "infralens-drift-${var.run_id}"
  description = "Isolated InfraLens drift test; no initial ingress or egress"
  vpc_id      = aws_vpc.demo.id
  ingress     = []
  egress      = []
}

resource "aws_instance" "demo" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.demo.id
  vpc_security_group_ids      = [aws_security_group.demo.id]
  associate_public_ip_address = false
  monitoring                  = false
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  credit_specification {
    cpu_credits = "standard"
  }
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    encrypted             = true
    delete_on_termination = true
  }
  volume_tags = {
    Project = "InfraLens"
    Purpose = "DriftSandbox"
    RunId   = var.run_id
  }
  tags = { Name = "infralens-drift-${var.run_id}" }
}

output "sandbox" {
  value = {
    account_id        = var.account_id
    region            = var.region
    run_id            = var.run_id
    instance_id       = aws_instance.demo.id
    security_group_id = aws_security_group.demo.id
    vpc_id            = aws_vpc.demo.id
    subnet_id         = aws_subnet.demo.id
  }
}
