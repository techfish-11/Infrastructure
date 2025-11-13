output "grafana_url" {
  description = "URL to access Grafana"
  value       = "http://localhost:3000"
}

output "ntopng_url" {
  description = "URL to access ntopng"
  value       = "http://localhost:3001"
}

output "redis_url" {
  description = "Redis connection URL"
  value       = "redis://localhost:6379"
}
