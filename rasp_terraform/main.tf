terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  host = "unix:///var/run/docker.sock"
}

# Grafana container
resource "docker_container" "grafana" {
  name  = "grafana"
  image = "grafana/grafana:latest"

  ports {
    internal = 3000
    external = 3000
  }

  volumes {
    host_path      = "/var/lib/grafana"
    container_path = "/var/lib/grafana"
  }

  env = [
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_admin_password}"
  ]

  restart = "unless-stopped"
}

# ntopng container
resource "docker_container" "ntopng" {
  name  = "ntopng"
  image = "ntop/ntopng:latest"

  ports {
    internal = 3000
    external = 3001
  }

  env = [
    "NTOPNG_LICENSE=${var.ntopng_license}",
    "NTOPNG_REDIS_HOST=redis"
  ]

  volumes {
    host_path      = "/var/lib/ntopng"
    container_path = "/var/lib/ntopng"
  }

  # Network mode host for network monitoring
  network_mode = "host"

  restart = "unless-stopped"
}

# Redis for ntopng (if needed)
resource "docker_container" "redis" {
  name  = "redis"
  image = "redis:alpine"

  ports {
    internal = 6379
    external = 6379
  }

  restart = "unless-stopped"
}
