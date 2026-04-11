# Root variables — passed through to the obsidian_palace module.
# All sensitive values are set as Terraform Cloud workspace variables.

variable "project_id" {
  description = "GCP project ID."
  type        = string
  default     = "obsidianpalace"
}

variable "region" {
  description = "GCP region for all regional resources."
  type        = string
  default     = "us-central1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "region must be a valid GCP region."
  }
}

variable "zone" {
  description = "GCP zone for the compute instance."
  type        = string
  default     = "us-central1-a"
}

variable "container_image" {
  description = "Docker image URI for the ObsidianPalace container."
  type        = string
}

# --- Secrets (set in Terraform Cloud) ---

variable "google_oauth_client_id" {
  description = "Google OAuth 2.0 client ID."
  type        = string
  sensitive   = true
}

variable "google_oauth_client_secret" {
  description = "Google OAuth 2.0 client secret."
  type        = string
  sensitive   = true
}

variable "allowed_email" {
  description = "Google account email permitted to access the MCP server."
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key for AI-assisted note placement."
  type        = string
  sensitive   = true
}

variable "obsidian_sync_credentials" {
  description = "Obsidian Sync credential file contents (base64-encoded)."
  type        = string
  sensitive   = true
}

# --- Optional overrides ---

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed SSH access to the instance."
  type        = list(string)
  default     = []
}

variable "allowed_https_cidrs" {
  description = "Additional CIDR blocks for HTTPS access (empty = allow all, rely on OAuth)."
  type        = list(string)
  default     = []
}
