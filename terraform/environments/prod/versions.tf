terraform {
  cloud {
    organization = "TheWinterShadow"

    workspaces {
      name = "obsidian-palace"
    }
  }

  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }
}
