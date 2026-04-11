# --- Required ---

variable "project_id" {
  description = "GCP project ID where ObsidianPalace resources are deployed."
  type        = string

  validation {
    condition     = length(var.project_id) > 0
    error_message = "project_id must not be empty."
  }
}

variable "region" {
  description = "GCP region for all regional resources."
  type        = string
  default     = "us-central1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "region must be a valid GCP region (e.g. us-central1, europe-west1)."
  }
}

variable "zone" {
  description = "GCP zone for the compute instance."
  type        = string
  default     = "us-central1-a"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]-[a-z]$", var.zone))
    error_message = "zone must be a valid GCP zone (e.g. us-central1-a)."
  }
}

variable "domain" {
  description = "Domain name for the ObsidianPalace service (e.g. lifeos.thewintershadow.com)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.domain))
    error_message = "domain must be a valid hostname."
  }
}

# --- Container ---

variable "container_image" {
  description = "Docker image URI for the ObsidianPalace container (e.g. gcr.io/obsidianpalace/obsidian-palace:latest)."
  type        = string

  validation {
    condition     = length(var.container_image) > 0
    error_message = "container_image must not be empty."
  }
}

# --- Secrets ---

variable "google_oauth_client_id" {
  description = "Google OAuth 2.0 client ID for authentication."
  type        = string
  sensitive   = true
}

variable "google_oauth_client_secret" {
  description = "Google OAuth 2.0 client secret for authentication."
  type        = string
  sensitive   = true
}

variable "allowed_email" {
  description = "Google account email permitted to access the MCP server."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("@", var.allowed_email))
    error_message = "allowed_email must be a valid email address."
  }
}

variable "anthropic_api_key" {
  description = "Anthropic API key for AI-assisted note placement."
  type        = string
  sensitive   = true
}

variable "obsidian_sync_credentials" {
  description = "Obsidian Sync credential file contents (base64-encoded), injected at container startup."
  type        = string
  sensitive   = true
}

# --- Optional ---

variable "machine_type" {
  description = "GCE machine type. e2-small (2 GB RAM) is minimum for vault + ChromaDB."
  type        = string
  default     = "e2-small"
}

variable "disk_size_gb" {
  description = "Size of the persistent data disk in GB (vault + ChromaDB)."
  type        = number
  default     = 20

  validation {
    condition     = var.disk_size_gb >= 10
    error_message = "disk_size_gb must be at least 10 GB."
  }
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into the instance (for emergency access)."
  type        = list(string)
  default     = []
}

variable "allowed_https_cidrs" {
  description = "Additional CIDR blocks allowed HTTPS access beyond Anthropic's ranges."
  type        = list(string)
  default     = []
}
