# Cloud DNS — managed zone and A record pointing to the static IP.

resource "google_dns_managed_zone" "obsidian_palace" {
  project     = var.project_id
  name        = var.dns_zone_name
  dns_name    = var.dns_managed_zone_dns_name
  description = "DNS zone for ObsidianPalace (${var.domain})"

  depends_on = [google_project_service.dns]
}

resource "google_dns_record_set" "a_record" {
  project      = var.project_id
  managed_zone = google_dns_managed_zone.obsidian_palace.name
  name         = "${var.domain}."
  type         = "A"
  ttl          = 300

  rrdatas = [google_compute_address.obsidian_palace.address]
}
