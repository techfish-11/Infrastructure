variable "grafana_admin_password" {
  description = "Admin password for Grafana"
  type        = string
  default     = "admin"
  sensitive   = true
}

variable "ntopng_license" {
  description = "License key for ntopng (optional)"
  type        = string
  default     = ""
}
