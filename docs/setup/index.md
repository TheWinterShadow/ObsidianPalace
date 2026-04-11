---
title: Setup Guide
description: Deploy your own ObsidianPalace instance from scratch.
icon: material/clipboard-check-outline
---

# Setup Guide

This guide walks you through deploying your own ObsidianPalace instance. By the end, you'll have a running MCP server that gives Claude (and any MCP client) full read/write/search access to your Obsidian vault.

**Time estimate**: 45--60 minutes for a first-time setup.

**Monthly cost**: ~$15 (GCE e2-small + persistent disk + static IP).

---

## Prerequisites

Before you begin, make sure you have the following:

| Requirement | Why |
|-------------|-----|
| A [GCP account](https://cloud.google.com/) with billing enabled | Hosts the VM, secrets, and container registry |
| [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5 | Provisions all infrastructure |
| A [Terraform Cloud](https://app.terraform.io/) account (free tier) | Stores Terraform state and runs applies |
| [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`) | Authenticates Docker pushes and SSH access |
| [Docker](https://docs.docker.com/get-docker/) | Builds the container image |
| [Node.js](https://nodejs.org/) >= 18 | Required to run `ob login` locally |
| An [Obsidian Sync](https://obsidian.md/sync) subscription | Keeps the vault in sync between your apps and the server |
| A domain name you control | For HTTPS and OAuth redirect URIs |
| A Google account (Gmail or Workspace) | Used for OAuth authentication -- this is the account that will be allowed access |
| An [Anthropic API key](https://console.anthropic.com/) | Powers AI-assisted note placement (optional but recommended) |

---

## Guide sections

The setup guide is split into three sections:

<div class="grid cards" markdown>

-   :material-rocket-launch-outline:{ .lg .middle } **Deployment**

    ---

    Create the GCP project, configure OAuth, set up Terraform Cloud, deploy infrastructure, build and push the Docker image, configure DNS and Obsidian Sync, and verify the deployment.

    [:octicons-arrow-right-24: Steps 1--10](deployment.md)

-   :material-lan-connect:{ .lg .middle } **Connecting Clients**

    ---

    Connect Claude Code, Claude Desktop, OpenCode, and other MCP clients to your running server.

    [:octicons-arrow-right-24: Connect a client](connection.md)

-   :material-bug-outline:{ .lg .middle } **Troubleshooting**

    ---

    Diagnose and fix common issues: SSL certs, Obsidian Sync, OAuth discovery, container startup, memory, and persistent disk.

    [:octicons-arrow-right-24: Troubleshooting](troubleshooting.md)

</div>
