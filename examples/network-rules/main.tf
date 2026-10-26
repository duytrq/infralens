# Offline source-location fixture paired with plan.json. No AWS deployment.
variable "ingress_group_id" { type = string }
variable "egress_group_id" { type = string }
variable "legacy_group_id" { type = string }

resource "aws_vpc_security_group_ingress_rule" "widen_ports" {
  security_group_id = var.ingress_group_id
  cidr_ipv4        = "0.0.0.0/0"
  ip_protocol      = "tcp"
  from_port        = 22
  to_port          = 22
}

resource "aws_vpc_security_group_ingress_rule" "new_ipv6" {
  security_group_id = var.ingress_group_id
  cidr_ipv6        = "2001:db8::/64"
  ip_protocol      = "tcp"
  from_port        = 443
  to_port          = 443
}

resource "aws_vpc_security_group_ingress_rule" "narrow_ports" {
  security_group_id = var.ingress_group_id
  cidr_ipv4        = "0.0.0.0/0"
  ip_protocol      = "tcp"
  from_port        = 443
  to_port          = 444
}

resource "aws_vpc_security_group_egress_rule" "widen_egress" {
  security_group_id = var.egress_group_id
  cidr_ipv4        = "0.0.0.0/0"
  ip_protocol      = "tcp"
  from_port        = 443
  to_port          = 443
}

resource "aws_security_group_rule" "legacy_direction" {
  security_group_id = var.legacy_group_id
  type              = "egress"
  cidr_blocks       = ["0.0.0.0/0"]
  protocol          = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_ingress_rule" "hidden_context" {
  security_group_id = var.ingress_group_id
  cidr_ipv4        = "10.0.0.0/24"
  ip_protocol      = "tcp"
  from_port        = 22
  to_port          = 22
}
