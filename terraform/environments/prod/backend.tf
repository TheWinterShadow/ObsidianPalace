# Alternative backend — GCS bucket for state storage.
# Currently using Terraform Cloud (see versions.tf).
#
# terraform {
#   backend "gcs" {
#     bucket = "obsidian-palace-tfstate"
#     prefix = "obsidian_palace/state"
#   }
# }
