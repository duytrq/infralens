# Offline review demo paired with plan.json; no AWS resources were deployed.
variable "ami" {
  type = string
}

resource "aws_security_group" "web" {
  name    = "example-drift-review"
  ingress = []
  egress  = []
}

resource "aws_instance" "missing" {
  ami           = var.ami
  instance_type = "t3.micro"
}

resource "aws_instance" "resized" {
  ami           = var.ami
  instance_type = "t3.micro"
}

resource "aws_instance" "tagged" {
  ami           = var.ami
  instance_type = "t3.micro"
  tags          = { AccessProject = "example-old" }
}
