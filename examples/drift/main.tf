# Offline demonstration paired with plan.json; no resources were deployed.
variable "ami" {
  type = string
}

resource "aws_instance" "demo" {
  ami           = var.ami
  instance_type = "t3.micro"
}
